"""Unit tests for leadgen.core.telemetry.ws_broadcaster."""

import asyncio
import json

import pytest

from leadgen.core.telemetry import ws_broadcaster
from leadgen.core.telemetry.ws_broadcaster import ws_broadcast_loop


class FakeWebSocket:
    def __init__(self, fail_on_send=False):
        self.sent = []
        self._fail_on_send = fail_on_send

    async def send_text(self, message):
        if self._fail_on_send:
            raise RuntimeError("socket closed")
        self.sent.append(message)


@pytest.fixture
def queue(monkeypatch):
    fresh = asyncio.Queue(maxsize=2000)
    monkeypatch.setattr(ws_broadcaster, "ws_queue", fresh)
    return fresh


@pytest.mark.asyncio
async def test_broadcast_forwards_queue_items_then_stream_end(queue):
    queue.put_nowait("one")
    queue.put_nowait("two")
    queue.put_nowait(None)

    websocket = FakeWebSocket()
    result = await ws_broadcast_loop(websocket)

    assert result is None
    assert websocket.sent[:2] == ["one", "two"]
    assert json.loads(websocket.sent[2]) == {"event_type": "stream_end"}
    assert queue.empty()


@pytest.mark.asyncio
async def test_broadcast_returns_on_none_sentinel(queue):
    queue.put_nowait(None)

    websocket = FakeWebSocket()
    await ws_broadcast_loop(websocket)

    assert len(websocket.sent) == 1
    assert json.loads(websocket.sent[0]) == {"event_type": "stream_end"}


@pytest.mark.asyncio
async def test_broadcast_send_failure_exits_without_raising(queue):
    queue.put_nowait("boom")

    websocket = FakeWebSocket(fail_on_send=True)
    await ws_broadcast_loop(websocket)

    assert websocket.sent == []
