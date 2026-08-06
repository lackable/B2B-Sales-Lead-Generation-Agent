"""
Async-safe WebSocket broadcast queue.

The WebSocketQueueHandler (in handlers.py) puts JSON strings here.
The FastAPI WebSocket endpoint reads from here and sends to connected clients.

Because agents run as subprocess children OR in-process coroutines, the queue
must survive import across module boundaries — it is a module-level singleton.
"""

import asyncio
from typing import Optional

# ── Singleton queue used by both the log handler and the WS broadcaster ────────
ws_queue: asyncio.Queue = asyncio.Queue(maxsize=2000)


async def ws_broadcast_loop(websocket) -> None:
    """
    Drain *ws_queue* and send each JSON string to the connected WebSocket client.

    Call this inside a FastAPI WebSocket endpoint after `await websocket.accept()`.
    Exits cleanly when the client disconnects or the queue receives a sentinel ``None``.
    """
    from starlette.websockets import WebSocketDisconnect  # lazy import — no hard dep on starlette
    try:
        while True:
            try:
                # Wait up to 30 s for the next item so we can detect a dead
                # connection even when the agent is idle.
                item: Optional[str] = await asyncio.wait_for(ws_queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send a keepalive ping so the browser doesn't close the socket.
                try:
                    await websocket.send_text('{"event_type":"keepalive"}')
                except Exception:
                    break
                continue

            if item is None:
                # Sentinel — run is finished; notify client then stop.
                try:
                    await websocket.send_text('{"event_type":"stream_end"}')
                except Exception:
                    pass
                break

            try:
                await websocket.send_text(item)
            except (WebSocketDisconnect, Exception):
                break
    except (WebSocketDisconnect, Exception):
        pass
