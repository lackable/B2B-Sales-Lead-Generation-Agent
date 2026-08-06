"""
Custom logging handlers for the pipeline logging system.

Three handlers are registered by setup_logging():

1. StructuredFileHandler  — writes JSON Lines to a rotating file (indefinite retention).
2. CentralLogHandler      — HTTP-POSTs batches to a Loki/Elastic endpoint (env-driven).
3. WebSocketQueueHandler  — puts JSON strings into the ws_queue singleton for live streaming.

All handlers serialise the record using _build_envelope() which enforces the schema
defined in schema.py and applies API-key redaction before emission.
"""

import json
import logging
import logging.handlers
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from itertools import count
from typing import Optional

from logging_utils.redact import redact
from logging_utils.ws_broadcaster import ws_queue

SCHEMA_VERSION = "1.1"
_event_sequence = count(1)
_event_sequence_lock = threading.Lock()


def _build_envelope(record: logging.LogRecord) -> dict:
    """
    Convert a LogRecord into the canonical event envelope dict.

    The LogRecord must carry extra fields set by StructuredLoggerAdapter:
      - agent       : str
      - run_id      : str
      - event_type  : str
      - data        : dict  (event-specific payload, will be redacted)
      - component   : str   (defaults to record.name)
      - correlation_id : str | None
    """
    cached = getattr(record, "_structured_envelope", None)
    if cached is not None:
        return cached

    raw_data = getattr(record, "data", {}) or {}
    event_type = getattr(record, "event_type", "log")
    agent = getattr(record, "agent", "unknown")
    run_id = getattr(record, "run_id", "unknown")
    component = getattr(record, "component", record.name)
    correlation_id = getattr(record, "correlation_id", None)

    with _event_sequence_lock:
        sequence = next(_event_sequence)

    envelope = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "sequence": sequence,
        "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
        "level": record.levelname,
        "run_id": run_id,
        "agent": agent,
        "component": component,
        "event_type": event_type,
        "correlation_id": correlation_id,
        "parent_run_id": getattr(record, "parent_run_id", None),
        "execution_id": getattr(record, "execution_id", None),
        "parent_execution_id": getattr(record, "parent_execution_id", None),
        "company": getattr(record, "company", None),
        "branch": getattr(record, "branch", None),
        "data": redact(raw_data),
    }
    record._structured_envelope = envelope
    return envelope


# ─────────────────────────────────────────────────────────────────────────────
# 1. Rotating JSONL file handler
# ─────────────────────────────────────────────────────────────────────────────

class StructuredFileHandler(logging.handlers.RotatingFileHandler):
    """
    Writes one JSON-encoded envelope per line to a rotating log file.

    maxBytes=50 MB  — rotate when a shard reaches 50 MB.
    backupCount=0   — keep ALL shards (indefinite retention).
    """

    def __init__(self, log_file: str):
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        super().__init__(
            filename=log_file,
            maxBytes=50 * 1024 * 1024,  # 50 MB
            backupCount=0,               # keep everything
            encoding="utf-8",
            delay=True,
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            envelope = _build_envelope(record)
            line = json.dumps(envelope, default=str, ensure_ascii=False) + "\n"
            # Bypass RotatingFileHandler.emit() to control the exact line written.
            self.acquire()
            try:
                if self.shouldRollover(record):
                    self.doRollover()
                stream = self.stream
                if stream is None:
                    stream = self._open()
                stream.write(line)
                stream.flush()
            finally:
                self.release()
        except Exception:
            self.handleError(record)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Central log server handler (Loki / Elastic / any HTTP endpoint)
# ─────────────────────────────────────────────────────────────────────────────

class CentralLogHandler(logging.Handler):
    """
    Batches log records and HTTP-POSTs them to CENTRAL_LOG_URL.

    Silently no-ops if CENTRAL_LOG_URL is not set in the environment.
    Batching is controlled by CENTRAL_LOG_BATCH_SIZE (default 50) and
    CENTRAL_LOG_FLUSH_INTERVAL_S (default 5 s).
    Uses a background daemon thread for the flush so the agent is never blocked.
    """

    def __init__(self):
        super().__init__()
        self._url: Optional[str] = os.getenv("CENTRAL_LOG_URL", "").strip() or None
        self._batch_size: int = int(os.getenv("CENTRAL_LOG_BATCH_SIZE", "50"))
        self._flush_interval: float = float(os.getenv("CENTRAL_LOG_FLUSH_INTERVAL_S", "5"))
        self._buffer: list = []
        self._lock = threading.Lock()
        self._last_flush = time.monotonic()

        if self._url:
            t = threading.Thread(target=self._flush_loop, daemon=True)
            t.start()

    def emit(self, record: logging.LogRecord) -> None:
        if not self._url:
            return
        try:
            envelope = _build_envelope(record)
            with self._lock:
                self._buffer.append(envelope)
                should_flush = (
                    len(self._buffer) >= self._batch_size
                    or time.monotonic() - self._last_flush >= self._flush_interval
                )
            if should_flush:
                self._flush()
        except Exception:
            self.handleError(record)

    def _flush_loop(self) -> None:
        while True:
            time.sleep(self._flush_interval)
            self._flush()

    def _flush(self) -> None:
        if not self._url:
            return
        with self._lock:
            if not self._buffer:
                return
            batch = self._buffer[:]
            self._buffer.clear()
            self._last_flush = time.monotonic()

        try:
            import urllib.request, urllib.error
            payload = json.dumps({"records": batch}, default=str).encode("utf-8")
            req = urllib.request.Request(
                self._url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass  # Central log server is best-effort; never crash the agent


# ─────────────────────────────────────────────────────────────────────────────
# 3. WebSocket queue handler
# ─────────────────────────────────────────────────────────────────────────────

class WebSocketQueueHandler(logging.Handler):
    """
    Serialises each log record as a JSON string and puts it onto ws_queue
    (the asyncio.Queue read by the FastAPI WebSocket broadcaster).

    Non-blocking: if the queue is full the record is silently dropped so the
    agent is never stalled by a slow or disconnected browser client.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            envelope = _build_envelope(record)
            line = json.dumps(envelope, default=str, ensure_ascii=False)
            ws_queue.put_nowait(line)
        except Exception:
            pass  # Never crash the agent due to logging
