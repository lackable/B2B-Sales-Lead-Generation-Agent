"""Unit tests for leadgen.core.telemetry.log_store."""

import json
import logging
import os

import pytest

from leadgen.core.telemetry import log_store, registry
from leadgen.core.telemetry.log_store import LogStore, set_logger


class CapturingLogger:
    def __init__(self):
        self.events = []

    def event(self, event_type, data, **kwargs):
        self.events.append({"event_type": event_type, "data": data, **kwargs})


@pytest.fixture(autouse=True)
def _reset_logger_and_registry(monkeypatch):
    monkeypatch.setattr(log_store, "_logger", None)
    previous = registry.get_logger()
    registry.register_logger(None)
    yield
    registry.register_logger(previous)


def test_log_file_uses_config_log_dir_and_run_id(isolated_var):
    store = LogStore(run_id="abc-123_XY")
    assert store.run_id == "abc-123_XY"
    assert store.log_file == os.path.join(os.path.abspath(isolated_var / "logs"), "run_abc-123_XY.jsonl")


def test_log_file_strips_unsafe_characters(isolated_var):
    store = LogStore(run_id="a b/c!d")
    assert store.run_id == "abcd"
    assert store.log_file == os.path.join(os.path.abspath(isolated_var / "logs"), "run_abcd.jsonl")


def test_log_file_empty_run_id_becomes_default(isolated_var):
    assert LogStore(run_id="").run_id == "default"
    assert LogStore(run_id="###").run_id == "default"
    assert os.path.basename(LogStore(run_id="").log_file) == "run_default.jsonl"


def test_write_event_routes_through_registry_when_registered():
    logger = CapturingLogger()
    registry.register_logger(logger)
    LogStore(run_id="r").write_event("node_enter", {"node": "x"})
    assert logger.events == [
        {
            "event_type": "node_enter",
            "data": {"node": "x"},
            "level": logging.INFO,
            "component": "core.telemetry.log_store",
        }
    ]


def test_write_event_falls_back_to_injected_logger(monkeypatch):
    injected = CapturingLogger()
    monkeypatch.setattr(log_store, "_logger", injected)
    LogStore(run_id="r").write_event("node_enter", {"node": "x"})
    assert injected.events == [
        {"event_type": "node_enter", "data": {"node": "x"}, "component": "core.telemetry.log_store"}
    ]


def test_write_event_falls_back_to_stderr_json(capsys):
    LogStore(run_id="run-9").write_event("node_enter", {"node": "x"})
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err.strip())
    assert payload["run_id"] == "run-9"
    assert payload["event_type"] == "node_enter"
    assert payload["data"] == {"node": "x"}
    assert "timestamp" in payload


def test_set_logger_sets_global_and_registers():
    logger = CapturingLogger()
    set_logger(logger)
    assert log_store._logger is logger
    assert registry.get_logger() is logger
