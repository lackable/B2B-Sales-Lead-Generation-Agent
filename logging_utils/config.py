"""
setup_logging() — call once at process start in each agent's main.py.

Returns a logging.LoggerAdapter with `agent` and `run_id` baked in.

Architecture
------------
LogRecord → QueueHandler (non-blocking, in agent thread)
                └─► QueueListener (background daemon thread)
                        ├─► StructuredFileHandler   → JSONL rotating file
                        ├─► CentralLogHandler       → Loki/Elastic (optional)
                        └─► WebSocketQueueHandler   → asyncio queue → browser WS

Environment variables
---------------------
LOG_LEVEL      : Python log level name (default INFO)
LOG_DIR        : Directory for JSONL log files (default logs/)
CENTRAL_LOG_URL: HTTP endpoint for central log server (optional)
"""

import logging
import logging.handlers
import os
import sys
from typing import Optional

from logging_utils.context import get_log_context

from logging_utils.handlers import (
    CentralLogHandler,
    StructuredFileHandler,
    WebSocketQueueHandler,
)
from logging_utils.registry import register_logger

_listener: Optional[logging.handlers.QueueListener] = None
_setup_done: bool = False


def setup_logging(agent: str, run_id: str) -> logging.LoggerAdapter:
    """
    Configure the root pipeline logger with async QueueHandler.

    Safe to call multiple times — subsequent calls update the adapter bindings
    but do not add duplicate handlers.

    Returns
    -------
    logging.LoggerAdapter
        A logger that automatically injects ``agent`` and ``run_id`` into every
        LogRecord's extra dict. Emit structured events with::

            logger.info("node_enter", extra={"event_type": "node_enter", "data": {...}})
    """
    global _listener, _setup_done

    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    log_dir = os.getenv("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)
    safe_run_id = "".join(c for c in str(run_id) if c.isalnum() or c in ("-", "_")).strip() or "default"
    log_file = os.path.join(log_dir, f"run_{safe_run_id}.jsonl")

    root_logger = logging.getLogger("pipeline")
    root_logger.setLevel(log_level)

    if not _setup_done:
        # Build the real handlers
        file_handler = StructuredFileHandler(log_file)
        file_handler.setLevel(log_level)

        central_handler = CentralLogHandler()
        central_handler.setLevel(log_level)

        ws_handler = WebSocketQueueHandler()
        ws_handler.setLevel(log_level)

        # Also keep a simple stderr handler so operators see logs in the terminal
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.WARNING)
        stderr_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        stderr_handler.setFormatter(stderr_fmt)

        # Async queue to decouple agent from handler I/O
        log_queue: "logging.handlers.Queue" = logging.handlers.QueueHandler.__new__(
            logging.handlers.QueueHandler
        )
        import queue as _queue_mod
        q = _queue_mod.Queue(maxsize=-1)  # unbounded — drops nothing

        queue_handler = logging.handlers.QueueHandler(q)
        queue_handler.setLevel(log_level)

        _listener = logging.handlers.QueueListener(
            q,
            file_handler,
            central_handler,
            ws_handler,
            stderr_handler,
            respect_handler_level=True,
        )
        _listener.start()

        # Attach only the queue handler to the logger — it enqueues non-blocking
        root_logger.handlers.clear()
        root_logger.addHandler(queue_handler)
        root_logger.propagate = False
        _setup_done = True

    # Wrap in an adapter that injects agent/run_id into every record's `extra`
    adapter = StructuredLoggerAdapter(root_logger, agent=agent, run_id=run_id)
    register_logger(adapter)
    return adapter


class StructuredLoggerAdapter(logging.LoggerAdapter):
    """
    LoggerAdapter that merges ``agent``, ``run_id``, and caller component into
    every LogRecord so handlers can read them without per-call boilerplate.
    """

    def __init__(self, logger: logging.Logger, agent: str, run_id: str):
        super().__init__(logger, extra={})
        self._agent = agent
        self._run_id = run_id

    def process(self, msg, kwargs):
        extra = kwargs.get("extra") or {}
        context = get_log_context()
        extra["agent"] = context.get("agent", extra.get("agent", self._agent))
        extra["run_id"] = context.get("run_id", extra.get("run_id", self._run_id))
        extra.setdefault("event_type", "log")
        extra.setdefault("data", {})
        extra.setdefault("component", "unknown")
        extra.setdefault("correlation_id", None)
        for field in (
            "parent_run_id",
            "execution_id",
            "parent_execution_id",
            "company",
            "branch",
        ):
            if field in context:
                extra[field] = context[field]
        kwargs["extra"] = extra
        return msg, kwargs

    # ── Convenience helpers ─────────────────────────────────────────────────

    def event(self, event_type: str, data: dict, *, level: int = logging.INFO,
               component: str = "unknown", correlation_id=None) -> None:
        """
        Emit a single structured log event.

        Example::
            logger.event("node_enter", {"node_name": "query_formulator", "step_num": 1})
        """
        self.log(
            level,
            event_type,
            extra={
                "event_type": event_type,
                "data": data,
                "component": component,
                "correlation_id": correlation_id,
                "agent": self._agent,
                "run_id": self._run_id,
            },
        )
