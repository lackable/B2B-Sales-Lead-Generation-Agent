"""Unit tests for leadgen.core.telemetry.handlers."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

import pytest

from leadgen.core.telemetry import handlers
from leadgen.core.telemetry.handlers import (
    CentralLogHandler,
    StructuredFileHandler,
    WebSocketQueueHandler,
    _build_envelope,
)

ENVELOPE_KEYS = {
    "schema_version",
    "event_id",
    "sequence",
    "timestamp",
    "level",
    "run_id",
    "agent",
    "component",
    "event_type",
    "correlation_id",
    "parent_run_id",
    "execution_id",
    "parent_execution_id",
    "company",
    "branch",
    "data",
}


def _make_record(**attrs) -> logging.LogRecord:
    record = logging.LogRecord(
        name=attrs.pop("name", "pipeline"),
        level=attrs.pop("level", logging.INFO),
        pathname=__file__,
        lineno=1,
        msg=attrs.pop("msg", "event"),
        args=(),
        exc_info=None,
    )
    for key, value in attrs.items():
        setattr(record, key, value)
    return record


@pytest.fixture
def fresh_ws_queue(monkeypatch):
    queue = asyncio.Queue(maxsize=2000)
    monkeypatch.setattr(handlers, "ws_queue", queue)
    return queue


# ── _build_envelope ──────────────────────────────────────────────────────────


def test_build_envelope_has_exact_keys_and_values():
    record = _make_record(
        level=logging.WARNING,
        agent="shortlister",
        run_id="run-1",
        event_type="node_enter",
        data={"node": "query"},
        component="agent.node",
        correlation_id="corr-1",
        parent_run_id="pr",
        execution_id="e1",
        parent_execution_id="pe1",
        company="Acme",
        branch="b1",
    )
    record.created = 0.0

    envelope = _build_envelope(record)

    assert set(envelope) == ENVELOPE_KEYS
    assert envelope["schema_version"] == "1.1"
    assert uuid.UUID(envelope["event_id"])
    assert isinstance(envelope["sequence"], int)
    assert envelope["timestamp"] == datetime.fromtimestamp(0.0, tz=timezone.utc).isoformat()
    assert envelope["level"] == "WARNING"
    assert envelope["run_id"] == "run-1"
    assert envelope["agent"] == "shortlister"
    assert envelope["component"] == "agent.node"
    assert envelope["event_type"] == "node_enter"
    assert envelope["correlation_id"] == "corr-1"
    assert envelope["parent_run_id"] == "pr"
    assert envelope["execution_id"] == "e1"
    assert envelope["parent_execution_id"] == "pe1"
    assert envelope["company"] == "Acme"
    assert envelope["branch"] == "b1"
    assert envelope["data"] == {"node": "query"}


def test_build_envelope_defaults_for_bare_record():
    envelope = _build_envelope(_make_record(name="my.logger"))

    assert envelope["event_type"] == "log"
    assert envelope["agent"] == "unknown"
    assert envelope["run_id"] == "unknown"
    assert envelope["component"] == "my.logger"
    assert envelope["correlation_id"] is None
    assert envelope["parent_run_id"] is None
    assert envelope["execution_id"] is None
    assert envelope["parent_execution_id"] is None
    assert envelope["company"] is None
    assert envelope["branch"] is None
    assert envelope["data"] == {}
    assert envelope["level"] == "INFO"


def test_build_envelope_redacts_data():
    record = _make_record(data={"api_key": "secret", "nested": {"token": "t", "ok": 1}})
    assert _build_envelope(record)["data"] == {"api_key": "***", "nested": {"token": "***", "ok": 1}}


def test_build_envelope_sequence_is_monotonically_increasing():
    first = _build_envelope(_make_record())
    second = _build_envelope(_make_record())
    assert second["sequence"] - first["sequence"] == 1


def test_build_envelope_caches_on_record():
    record = _make_record(event_type="evt")
    first = _build_envelope(record)
    second = _build_envelope(record)
    assert first is second
    assert getattr(record, "_structured_envelope") is first


def test_build_envelope_reuses_cached_envelope_even_after_mutation():
    record = _make_record(event_type="evt", data={"a": 1})
    first = _build_envelope(record)
    record.data = {"a": 2}
    assert _build_envelope(record) is first
    assert _build_envelope(record)["data"] == {"a": 1}


# ── StructuredFileHandler ────────────────────────────────────────────────────


def test_structured_file_handler_rotation_config(tmp_path):
    handler = StructuredFileHandler(str(tmp_path / "run.jsonl"))
    try:
        assert handler.maxBytes == 50 * 1024 * 1024
        assert handler.backupCount == 0
    finally:
        handler.close()


def test_structured_file_handler_writes_one_json_line_per_record(tmp_path):
    log_file = tmp_path / "nested" / "dir" / "run.jsonl"
    handler = StructuredFileHandler(str(log_file))
    try:
        assert log_file.parent.is_dir()
        handler.emit(_make_record(event_type="evt1", agent="a", run_id="r"))
        handler.emit(_make_record(event_type="evt2", agent="a", run_id="r"))
        handler.flush()
    finally:
        handler.close()

    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert [entry["event_type"] for entry in parsed] == ["evt1", "evt2"]
    assert parsed[0]["schema_version"] == "1.1"
    assert parsed[0]["agent"] == "a"
    assert parsed[0]["run_id"] == "r"


# ── WebSocketQueueHandler ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_websocket_queue_handler_puts_json_string(fresh_ws_queue):
    handler = WebSocketQueueHandler()
    handler.emit(_make_record(event_type="node_enter", agent="a", run_id="r", data={"k": "v"}))

    item = await asyncio.wait_for(fresh_ws_queue.get(), timeout=1.0)
    payload = json.loads(item)
    assert payload["event_type"] == "node_enter"
    assert payload["agent"] == "a"
    assert payload["run_id"] == "r"
    assert payload["data"] == {"k": "v"}
    assert fresh_ws_queue.empty()


@pytest.mark.asyncio
async def test_websocket_queue_handler_swallows_bad_record(monkeypatch, fresh_ws_queue):
    def _boom(record):
        raise ValueError("bad record")

    monkeypatch.setattr(handlers, "_build_envelope", _boom)

    WebSocketQueueHandler().emit(_make_record())

    await asyncio.sleep(0)
    assert fresh_ws_queue.empty()


# ── CentralLogHandler ────────────────────────────────────────────────────────


def test_central_log_handler_is_noop_without_url(monkeypatch):
    monkeypatch.delenv("CENTRAL_LOG_URL", raising=False)
    handler = CentralLogHandler()

    assert handler._url is None
    handler.emit(_make_record(event_type="evt"))
    assert handler._buffer == []
    handler._flush()
    assert handler._buffer == []


def test_central_log_handler_treats_blank_url_as_unset(monkeypatch):
    monkeypatch.setenv("CENTRAL_LOG_URL", "   ")
    assert CentralLogHandler()._url is None


def test_central_log_handler_reads_batch_settings(monkeypatch):
    monkeypatch.delenv("CENTRAL_LOG_URL", raising=False)
    monkeypatch.setenv("CENTRAL_LOG_BATCH_SIZE", "7")
    monkeypatch.setenv("CENTRAL_LOG_FLUSH_INTERVAL_S", "2.5")

    handler = CentralLogHandler()
    assert handler._batch_size == 7
    assert handler._flush_interval == 2.5
