"""Unit tests for leadgen.core.telemetry.registry."""

import logging

import pytest

from leadgen.core.telemetry import registry


class CapturingLogger:
    def __init__(self):
        self.events = []

    def event(self, event_type, data, **kwargs):
        self.events.append({"event_type": event_type, "data": data, **kwargs})


class ExplodingLogger:
    def event(self, event_type, data, **kwargs):
        raise RuntimeError("logger boom")


@pytest.fixture(autouse=True)
def _restore_registry():
    previous = registry.get_logger()
    yield
    registry.register_logger(previous)


def test_get_logger_returns_none_initially():
    registry.register_logger(None)
    assert registry.get_logger() is None


def test_register_and_get_logger_round_trip():
    logger = CapturingLogger()
    registry.register_logger(logger)
    assert registry.get_logger() is logger


def test_emit_event_returns_false_without_logger():
    registry.register_logger(None)
    assert registry.emit_event("evt", {"a": 1}) is False


def test_emit_event_returns_true_with_capturing_logger():
    logger = CapturingLogger()
    registry.register_logger(logger)
    assert registry.emit_event("evt", {"a": 1}, component="comp") is True
    assert logger.events == [{"event_type": "evt", "data": {"a": 1}, "level": logging.INFO, "component": "comp"}]


def test_emit_event_resolves_string_levels():
    logger = CapturingLogger()
    registry.register_logger(logger)
    registry.emit_event("evt1", {}, level="warning")
    registry.emit_event("evt2", {}, level="ERROR")
    registry.emit_event("evt3", {}, level="notalevel")
    assert [event["level"] for event in logger.events] == [logging.WARNING, logging.ERROR, logging.INFO]


def test_emit_event_passes_int_levels_through():
    logger = CapturingLogger()
    registry.register_logger(logger)
    registry.emit_event("evt", {}, level=logging.CRITICAL)
    assert logger.events[0]["level"] == logging.CRITICAL


def test_emit_event_default_component_is_unknown():
    logger = CapturingLogger()
    registry.register_logger(logger)
    registry.emit_event("evt", {})
    assert logger.events[0]["component"] == "unknown"


def test_emit_event_swallows_logger_exceptions():
    registry.register_logger(ExplodingLogger())
    assert registry.emit_event("evt", {}) is False


def test_emit_event_does_not_change_registered_logger():
    logger = CapturingLogger()
    registry.register_logger(logger)
    registry.emit_event("evt", {})
    assert registry.get_logger() is logger
