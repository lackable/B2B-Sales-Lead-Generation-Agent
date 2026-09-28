"""WebSocket endpoints: /ws/logs (structured telemetry) and /ws/visualizer (state graph).

Both handshakes require a valid session cookie and an allowed ``Origin``; a
failure closes the socket with code 1008 (policy violation).
"""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from leadgen.api.state import visualizer_broker, ws_log_clients
from leadgen.auth.dependencies import authenticate_websocket, get_auth_service
from leadgen.auth.service import AuthService
from leadgen.core.telemetry.ws_broadcaster import ws_queue

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/visualizer")
async def ws_visualizer(websocket: WebSocket, service: AuthService = Depends(get_auth_service)):
    """Stream live Shortlister JSONL telemetry to every connected browser."""
    if await authenticate_websocket(websocket, service) is None:
        return
    client_queue = visualizer_broker.subscribe()
    try:
        while True:
            try:
                payload = await asyncio.wait_for(client_queue.get(), timeout=25.0)
                await websocket.send_json(payload)
            except asyncio.TimeoutError:
                await websocket.send_json({
                    "stream_version": "1.0",
                    "type": "keepalive",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        visualizer_broker.unsubscribe(client_queue)


@router.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket, service: AuthService = Depends(get_auth_service)):
    """
    WebSocket endpoint that streams structured JSON log events emitted by
    the pipeline agents in real-time.

    Events are JSON objects matching the envelope schema:
    {
        "schema_version": "1.0",
        "timestamp": "<ISO-8601>",
        "level": "INFO",
        "run_id": "<session-id>",
        "agent": "shortlister" | "linkedin",
        "component": "<module>",
        "event_type": "pipeline_start" | "node_enter" | "node_exit" | "tool_start" |
                      "tool_end" | "tool_error" | "llm_start" | "llm_end" |
                      "chain_start" | "chain_end" | "pipeline_end" | "pipeline_error" |
                      "progress" | "company_enriched" | "company_dropped" |
                      "contact_found" | "company_contacts_snapshot" | "subagent_start" |
                      "subagent_error" | "subagent_end" | "search_query" | "mcp_connect" |
                      "mcp_error" | "log",
        "correlation_id": null,
        "data": { ... event-specific payload ... }
    }
    """
    if await authenticate_websocket(websocket, service) is None:
        return
    ws_log_clients.append(websocket)
    try:
        # Drain the shared ws_queue and forward each JSON line to this client.
        # Also relay any plain-text logs that arrive from runner.broadcast().
        while True:
            try:
                item = await asyncio.wait_for(ws_queue.get(), timeout=30.0)
                if item is None:
                    await websocket.send_text('{"event_type":"stream_end"}')
                    break
                await websocket.send_text(item)
            except asyncio.TimeoutError:
                # Keepalive ping
                try:
                    await websocket.send_text('{"event_type":"keepalive"}')
                except Exception:
                    break
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if websocket in ws_log_clients:
            ws_log_clients.remove(websocket)
