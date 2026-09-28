"""Unit tests for leadgen.core.telemetry.adapter."""

import asyncio
import json
import logging
import os

import pytest

from leadgen.core.telemetry import adapter, context as context_module, handlers, registry
from leadgen.core.telemetry.adapter import StructuredLoggerAdapter, setup_logging
from leadgen.core.telemetry.context import push_log_context, reset_log_context


@pytest.fixture(autouse=True)
def _isolated_context():
    token = context_module._log_context.set({})
    yield
    context_module._log_context.reset(token)


@pytest.fixture(autouse=True)
def _restore_registry():
    previous = registry.get_logger()
    yield
    registry.register_logger(previous)


@pytest.fixture
def isolated_ws_queue(monkeypatch):
    queue = asyncio.Queue(maxsize=2000)
    monkeypatch.setattr(handlers, "ws_queue", queue)
    return queue


def _make_logger(name):
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    return logger


# ── StructuredLoggerAdapter.process ──────────────────────────────────────────


def test_process_injects_defaults():
    adapter_obj = StructuredLoggerAdapter(_make_logger("t.defaults"), agent="shortlister", run_id="run-1")
    msg, kwargs = adapter_obj.process("hello", {})
    extra = kwargs["extra"]

    assert msg == "hello"
    assert extra["agent"] == "shortlister"
    assert extra["run_id"] == "run-1"
    assert extra["event_type"] == "log"
    assert extra["data"] == {}
    assert extra["component"] == "unknown"
    assert extra["correlation_id"] is None
    for field in ("parent_run_id", "execution_id", "parent_execution_id", "company", "branch"):
        assert field not in extra


def test_process_preserves_explicit_extra_values():
    adapter_obj = StructuredLoggerAdapter(_make_logger("t.extra"), agent="shortlister", run_id="run-1")
    _, kwargs = adapter_obj.process(
        "m",
        {
            "extra": {
                "event_type": "custom",
                "data": {"x": 1},
                "component": "c",
                "correlation_id": "cid",
                "agent": "explicit",
                "run_id": "er",
            }
        },
    )
    extra = kwargs["extra"]

    assert extra["event_type"] == "custom"
    assert extra["data"] == {"x": 1}
    assert extra["component"] == "c"
    assert extra["correlation_id"] == "cid"
    assert extra["agent"] == "explicit"
    assert extra["run_id"] == "er"


def test_process_copies_context_fields_and_prefers_context():
    adapter_obj = StructuredLoggerAdapter(_make_logger("t.ctx"), agent="shortlister", run_id="run-1")
    token = push_log_context(
        agent="ctx-agent",
        run_id="ctx-run",
        parent_run_id="pr",
        execution_id="e1",
        parent_execution_id="pe1",
        company="Acme",
        branch="b1",
    )
    try:
        _, kwargs = adapter_obj.process("m", {})
    finally:
        reset_log_context(token)
    extra = kwargs["extra"]

    assert extra["agent"] == "ctx-agent"
    assert extra["run_id"] == "ctx-run"
    assert extra["parent_run_id"] == "pr"
    assert extra["execution_id"] == "e1"
    assert extra["parent_execution_id"] == "pe1"
    assert extra["company"] == "Acme"
    assert extra["branch"] == "b1"


def test_process_omits_none_context_fields():
    adapter_obj = StructuredLoggerAdapter(_make_logger("t.none"), agent="a", run_id="r")
    token = push_log_context(company=None)
    try:
        _, kwargs = adapter_obj.process("m", {})
    finally:
        reset_log_context(token)
    assert "company" not in kwargs["extra"]


# ── StructuredLoggerAdapter.event ────────────────────────────────────────────


def _capture_log(captured):
    def _capturing_log(level, msg, *args, **kwargs):
        captured["level"] = level
        captured["msg"] = msg
        captured["kwargs"] = kwargs

    return _capturing_log


def test_event_forwards_level_component_and_correlation_id(monkeypatch):
    logger = _make_logger("t.event")
    captured = {}
    monkeypatch.setattr(logger, "log", _capture_log(captured))

    adapter_obj = StructuredLoggerAdapter(logger, agent="shortlister", run_id="run-1")
    adapter_obj.event("node_enter", {"node": "x"}, level=logging.WARNING, component="comp", correlation_id="cid")

    assert captured["level"] == logging.WARNING
    assert captured["msg"] == "node_enter"
    assert captured["kwargs"]["extra"] == {
        "event_type": "node_enter",
        "data": {"node": "x"},
        "component": "comp",
        "correlation_id": "cid",
        "agent": "shortlister",
        "run_id": "run-1",
    }


def test_event_defaults_level_component_and_correlation(monkeypatch):
    logger = _make_logger("t.event-defaults")
    captured = {}
    monkeypatch.setattr(logger, "log", _capture_log(captured))

    adapter_obj = StructuredLoggerAdapter(logger, agent="a", run_id="r")
    adapter_obj.event("evt", {})

    assert captured["level"] == logging.INFO
    extra = captured["kwargs"]["extra"]
    assert extra["component"] == "unknown"
    assert extra["correlation_id"] is None
    assert extra["agent"] == "a"
    assert extra["run_id"] == "r"


# ── setup_logging ────────────────────────────────────────────────────────────


def test_setup_logging_binds_registers_and_writes_jsonl(monkeypatch, isolated_var, isolated_ws_queue):
    monkeypatch.delenv("CENTRAL_LOG_URL", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.setattr(adapter, "_setup_done", False)

    logger = setup_logging(agent="shortlister", run_id="run-42")
    listener = adapter._listener
    try:
        assert logger._agent == "shortlister"
        assert logger._run_id == "run-42"
        assert registry.get_logger() is logger

        logger.event("node_enter", {"node": "x"})
        listener.stop()
        listener = None

        log_file = os.path.join(str(isolated_var / "logs"), "run_run-42.jsonl")
        assert os.path.isfile(log_file)
        with open(log_file, encoding="utf-8") as handle:
            lines = [line for line in handle.read().splitlines() if line]
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["event_type"] == "node_enter"
        assert payload["agent"] == "shortlister"
        assert payload["run_id"] == "run-42"
        assert payload["data"] == {"node": "x"}
    finally:
        if listener is not None:
            listener.stop()
        adapter._listener = None
        pipeline_logger = logging.getLogger("pipeline")
        pipeline_logger.handlers.clear()
        pipeline_logger.propagate = True
