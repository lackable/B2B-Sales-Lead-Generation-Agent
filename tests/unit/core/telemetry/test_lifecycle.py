"""Unit tests for leadgen.core.telemetry.lifecycle."""

import asyncio
import logging

import pytest

from leadgen.core.telemetry import registry
from leadgen.core.telemetry.lifecycle import subagent_lifecycle


class CapturingLogger:
    def __init__(self):
        self.events = []

    def event(self, event_type, data, **kwargs):
        self.events.append({"event_type": event_type, "data": dict(data), **kwargs})


@pytest.fixture
def capture():
    previous = registry.get_logger()
    logger = CapturingLogger()
    registry.register_logger(logger)
    yield logger
    registry.register_logger(previous)


LIFECYCLE_KWARGS = {
    "company": "Acme",
    "execution_id": "e1",
    "parent_execution_id": "p1",
    "branch": "company_research",
    "component": "test.component",
}


def test_normal_completion_emits_exactly_one_start_then_end(capture):
    with subagent_lifecycle(**LIFECYCLE_KWARGS) as terminal_data:
        assert isinstance(terminal_data, dict)
        terminal_data["contact_count"] = 3

    assert [event["event_type"] for event in capture.events] == ["subagent_start", "subagent_end"]

    start, end = capture.events
    assert start["data"] == {
        "company": "Acme",
        "execution_id": "e1",
        "parent_execution_id": "p1",
        "branch": "company_research",
    }
    assert start["component"] == "test.component"
    assert end["data"] == {
        "company": "Acme",
        "execution_id": "e1",
        "parent_execution_id": "p1",
        "branch": "company_research",
        "contact_count": 3,
        "status": "completed",
    }


def test_end_payload_without_terminal_data_has_completed_status(capture):
    with subagent_lifecycle(**LIFECYCLE_KWARGS):
        pass

    end = capture.events[-1]
    assert end["event_type"] == "subagent_end"
    assert end["data"]["status"] == "completed"
    assert "error" not in end["data"]


def test_exception_emits_error_then_end_and_reraises(capture):
    with pytest.raises(ValueError, match="boom"):
        with subagent_lifecycle(**LIFECYCLE_KWARGS):
            raise ValueError("boom")

    assert [event["event_type"] for event in capture.events] == [
        "subagent_start",
        "subagent_error",
        "subagent_end",
    ]

    _, error_event, end = capture.events
    assert error_event["data"]["status"] == "error"
    assert error_event["data"]["error"] == "boom"
    assert error_event["data"]["error_type"] == "ValueError"
    assert error_event["level"] == logging.WARNING
    assert end["data"]["status"] == "error"
    assert end["data"]["error"] == "boom"


def test_cancelled_error_marks_status_cancelled(capture):
    with pytest.raises(asyncio.CancelledError):
        with subagent_lifecycle(**LIFECYCLE_KWARGS):
            raise asyncio.CancelledError()

    assert [event["event_type"] for event in capture.events] == [
        "subagent_start",
        "subagent_error",
        "subagent_end",
    ]
    _, error_event, end = capture.events
    assert error_event["data"]["status"] == "cancelled"
    assert error_event["data"]["error_type"] == "CancelledError"
    assert end["data"]["status"] == "cancelled"


def test_terminal_data_written_before_exception_is_merged_into_end(capture):
    with pytest.raises(RuntimeError):
        with subagent_lifecycle(**LIFECYCLE_KWARGS) as terminal_data:
            terminal_data["company_id"] = 7
            raise RuntimeError("late failure")

    end = capture.events[-1]
    assert end["event_type"] == "subagent_end"
    assert end["data"]["company_id"] == 7
    assert end["data"]["status"] == "error"
