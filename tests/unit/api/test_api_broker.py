"""Unit tests for the WebSocket visualizer broker (JSONL tailing + fan-out)."""

import asyncio
import contextlib
import json
from datetime import datetime, timezone

import pytest

from leadgen.api.visualizer_broker import VisualizerBroker


async def stop_tail(broker: VisualizerBroker) -> None:
    """Cancel the broker's tail task so no task outlives the test."""
    task = broker.tail_task
    broker.tail_task = None
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


@pytest.fixture
def broker():
    return VisualizerBroker()


@pytest.fixture
def jsonl_path(tmp_path):
    return tmp_path / "run.jsonl"


class TestSubscription:
    @pytest.mark.asyncio
    async def test_subscribe_tracks_the_queue_and_unsubscribe_removes_it(self, broker):
        first = broker.subscribe()
        second = broker.subscribe()

        assert isinstance(first, asyncio.Queue)
        assert first.maxsize == 2000
        assert broker.clients == {first, second}

        broker.unsubscribe(first)

        assert broker.clients == {second}

    @pytest.mark.asyncio
    async def test_unsubscribe_is_idempotent_and_ignores_unknown_objects(self, broker):
        queue_ = broker.subscribe()

        broker.unsubscribe(queue_)
        broker.unsubscribe(queue_)
        broker.unsubscribe(object())

        assert broker.clients == set()

    @pytest.mark.asyncio
    async def test_publish_fans_out_to_every_subscriber(self, broker):
        first = broker.subscribe()
        second = broker.subscribe()
        payload = {"stream_version": "1.0", "type": "event", "event": {"n": 1}}

        await broker.publish(payload)

        assert first.get_nowait() == payload
        assert second.get_nowait() == payload
        assert first.empty() and second.empty()

    @pytest.mark.asyncio
    async def test_publish_without_subscribers_is_a_noop(self, broker):
        await broker.publish({"type": "event"})

        assert broker.clients == set()

    @pytest.mark.asyncio
    async def test_publish_drops_the_oldest_item_when_a_queue_is_full(self, broker):
        queue_ = asyncio.Queue(maxsize=2)
        broker.clients.add(queue_)
        await queue_.put("first")
        await queue_.put("second")
        assert queue_.full()

        await broker.publish("third")

        assert queue_.qsize() == 2
        assert queue_.get_nowait() == "second"
        assert queue_.get_nowait() == "third"


class TestBeginRun:
    @pytest.mark.asyncio
    async def test_publishes_run_started_and_prepares_the_tail(self, broker, jsonl_path):
        jsonl_path.write_text("", encoding="utf-8")
        queue_ = broker.subscribe()

        try:
            await broker.begin_run("run-1", jsonl_path)

            payload = queue_.get_nowait()
            assert set(payload) == {"stream_version", "type", "control", "run_id", "timestamp"}
            assert payload["stream_version"] == "1.0"
            assert payload["type"] == "control"
            assert payload["control"] == "run_started"
            assert payload["run_id"] == "run-1"
            timestamp = datetime.fromisoformat(payload["timestamp"])
            assert timestamp.tzinfo == timezone.utc
            assert timestamp.utcoffset().total_seconds() == 0

            assert broker.active_run_id == "run-1"
            assert broker.active_log_path == jsonl_path
            assert isinstance(broker.process_done, asyncio.Event)
            assert broker.process_done.is_set() is False
            assert broker.process_outcome == {"status": "running", "error": None}
            assert isinstance(broker.tail_task, asyncio.Task)
        finally:
            await stop_tail(broker)

    @pytest.mark.asyncio
    async def test_begin_run_cancels_the_previous_tail_task(self, broker, jsonl_path):
        jsonl_path.write_text("", encoding="utf-8")
        try:
            await broker.begin_run("run-1", jsonl_path)
            first_task = broker.tail_task

            await broker.begin_run("run-2", jsonl_path)

            assert first_task is not broker.tail_task
            assert first_task.cancelled() is True
            assert broker.active_run_id == "run-2"
        finally:
            await stop_tail(broker)

    @pytest.mark.asyncio
    async def test_control_payloads_are_seen_by_every_subscriber(self, broker, jsonl_path):
        jsonl_path.write_text("", encoding="utf-8")
        first = broker.subscribe()
        second = broker.subscribe()

        try:
            await broker.begin_run("run-shared", jsonl_path)

            assert first.get_nowait()["control"] == "run_started"
            assert second.get_nowait()["control"] == "run_started"
        finally:
            await stop_tail(broker)


class TestMarkProcessDone:
    @pytest.mark.asyncio
    async def test_ignores_a_run_id_that_is_not_active(self, broker, jsonl_path):
        jsonl_path.write_text("", encoding="utf-8")
        queue_ = broker.subscribe()

        try:
            await broker.begin_run("active-run", jsonl_path)
            assert queue_.get_nowait()["control"] == "run_started"

            await broker.mark_process_done("other-run", "error", error="nope")

            assert broker.process_outcome == {"status": "running", "error": None}
            assert broker.process_done.is_set() is False
            assert queue_.empty() is True

            await broker.mark_process_done("active-run", "done")

            assert broker.process_outcome == {"status": "done", "error": None}
            assert broker.process_done.is_set() is True
        finally:
            await stop_tail(broker)

    @pytest.mark.asyncio
    async def test_is_a_noop_before_any_run_started(self, broker):
        assert broker.active_run_id is None
        assert broker.process_done is None

        await broker.mark_process_done("run-1", "done")

        assert broker.process_outcome == {}
        assert broker.process_done is None


class TestTailJsonl:
    @pytest.mark.asyncio
    async def test_streams_events_skips_malformed_lines_and_flushes_partial_line(
        self, broker, jsonl_path, capsys
    ):
        first_event = {"event_type": "node_enter", "node_name": "llm_query_generator", "seq": 1}
        second_event = {"event_type": "node_exit", "node_name": "llm_query_generator", "seq": 2}
        trailing_event = {"event_type": "contact_found", "seq": 3}
        jsonl_path.write_text(
            json.dumps(first_event) + "\n"
            + "{ this is not json }\n"
            + json.dumps(second_event) + "\n"
            + json.dumps(trailing_event),  # no trailing newline: stays in the buffer
            encoding="utf-8",
        )
        queue_ = broker.subscribe()

        try:
            await broker.begin_run("run-ctx", jsonl_path)

            started = await asyncio.wait_for(queue_.get(), timeout=5)
            assert started["type"] == "control"
            assert started["control"] == "run_started"
            assert started["run_id"] == "run-ctx"

            first = await asyncio.wait_for(queue_.get(), timeout=5)
            assert first == {
                "stream_version": "1.0",
                "type": "event",
                "run_id": "run-ctx",
                "event": first_event,
            }

            second = await asyncio.wait_for(queue_.get(), timeout=5)
            assert second["type"] == "event"
            assert second["event"] == second_event

            await broker.mark_process_done("run-ctx", "done")

            flushed = await asyncio.wait_for(queue_.get(), timeout=10)
            assert flushed == {
                "stream_version": "1.0",
                "type": "event",
                "run_id": "run-ctx",
                "event": trailing_event,
            }

            completed = await asyncio.wait_for(queue_.get(), timeout=10)
            assert completed["type"] == "control"
            assert completed["control"] == "run_completed"
            assert completed["run_id"] == "run-ctx"
            assert completed["status"] == "done"
            assert completed["error"] is None
            assert datetime.fromisoformat(completed["timestamp"]).tzinfo == timezone.utc
            assert queue_.empty() is True

            captured = capsys.readouterr().out
            assert "[VISUALIZER] Skipping malformed JSONL event" in captured
        finally:
            await stop_tail(broker)

    @pytest.mark.asyncio
    async def test_malformed_trailing_buffer_is_dropped_and_run_failed_is_published(
        self, broker, jsonl_path
    ):
        jsonl_path.write_text(json.dumps({"a": 1}) + "\n{ broken", encoding="utf-8")
        queue_ = broker.subscribe()

        try:
            await broker.begin_run("run-bad-tail", jsonl_path)
            assert (await asyncio.wait_for(queue_.get(), timeout=5))["control"] == "run_started"

            event_payload = await asyncio.wait_for(queue_.get(), timeout=5)
            assert event_payload["event"] == {"a": 1}

            await broker.mark_process_done("run-bad-tail", "error", error="boom")

            failed = await asyncio.wait_for(queue_.get(), timeout=10)
            assert failed["type"] == "control"
            assert failed["control"] == "run_failed"
            assert failed["run_id"] == "run-bad-tail"
            assert failed["status"] == "error"
            assert failed["error"] == "boom"
            assert queue_.empty() is True
        finally:
            await stop_tail(broker)

    @pytest.mark.asyncio
    async def test_blank_lines_and_duplicate_reads_are_ignored(self, broker, jsonl_path):
        jsonl_path.write_text("\n\n" + json.dumps({"only": "event"}) + "\n\n", encoding="utf-8")
        queue_ = broker.subscribe()

        try:
            await broker.begin_run("run-blank", jsonl_path)
            assert (await asyncio.wait_for(queue_.get(), timeout=5))["control"] == "run_started"

            assert (await asyncio.wait_for(queue_.get(), timeout=5))["event"] == {"only": "event"}

            await broker.mark_process_done("run-blank", "done")
            assert (await asyncio.wait_for(queue_.get(), timeout=10))["control"] == "run_completed"

            # Blank lines must not be published as events.
            assert queue_.empty() is True
        finally:
            await stop_tail(broker)

    @pytest.mark.asyncio
    async def test_missing_log_file_yields_no_events_but_finishes(self, broker, tmp_path):
        missing = tmp_path / "does-not-exist.jsonl"
        queue_ = broker.subscribe()

        try:
            await broker.begin_run("run-missing", missing)
            assert (await asyncio.wait_for(queue_.get(), timeout=5))["control"] == "run_started"

            await broker.mark_process_done("run-missing", "done")

            completed = await asyncio.wait_for(queue_.get(), timeout=10)
            assert completed["control"] == "run_completed"
            assert completed["status"] == "done"
        finally:
            await stop_tail(broker)

    @pytest.mark.asyncio
    async def test_appended_lines_are_read_incrementally(self, broker, jsonl_path):
        jsonl_path.write_text(json.dumps({"seq": 1}) + "\n", encoding="utf-8")
        queue_ = broker.subscribe()

        try:
            await broker.begin_run("run-append", jsonl_path)
            assert (await asyncio.wait_for(queue_.get(), timeout=5))["control"] == "run_started"
            assert (await asyncio.wait_for(queue_.get(), timeout=5))["event"] == {"seq": 1}

            with jsonl_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"seq": 2}) + "\n")

            appended = await asyncio.wait_for(queue_.get(), timeout=10)
            assert appended["event"] == {"seq": 2}

            await broker.mark_process_done("run-append", "done")
            assert (await asyncio.wait_for(queue_.get(), timeout=10))["control"] == "run_completed"
        finally:
            await stop_tail(broker)

    @pytest.mark.asyncio
    async def test_tail_task_finishes_after_run_completed(self, broker, jsonl_path):
        jsonl_path.write_text(json.dumps({"seq": 1}) + "\n", encoding="utf-8")
        queue_ = broker.subscribe()

        try:
            await broker.begin_run("run-finish", jsonl_path)
            await asyncio.wait_for(queue_.get(), timeout=5)
            await asyncio.wait_for(queue_.get(), timeout=5)
            await broker.mark_process_done("run-finish", "done")
            tail_task = broker.tail_task

            await asyncio.wait_for(queue_.get(), timeout=10)

            await asyncio.wait_for(tail_task, timeout=5)
            assert tail_task.done() is True
            assert broker.active_run_id == "run-finish"
        finally:
            await stop_tail(broker)
