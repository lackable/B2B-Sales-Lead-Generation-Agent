"""Live JSONL tailing and multi-client WebSocket fan-out."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Set


class VisualizerBroker:
    """Tail the active run's JSONL and fan events out to every WS client."""

    def __init__(self) -> None:
        self.clients: Set[asyncio.Queue] = set()
        self.active_run_id: Optional[str] = None
        self.active_log_path: Optional[Path] = None
        self.tail_task: Optional[asyncio.Task] = None
        self.process_done: Optional[asyncio.Event] = None
        self.process_outcome: Dict[str, Optional[str]] = {}

    def subscribe(self) -> asyncio.Queue:
        queue_: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self.clients.add(queue_)
        return queue_

    def unsubscribe(self, queue_: asyncio.Queue) -> None:
        self.clients.discard(queue_)

    async def publish(self, payload: dict) -> None:
        for queue_ in list(self.clients):
            if queue_.full():
                try:
                    queue_.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue_.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    async def begin_run(self, run_id: str, log_path: Path) -> None:
        if self.tail_task and not self.tail_task.done():
            self.tail_task.cancel()
            try:
                await self.tail_task
            except (asyncio.CancelledError, Exception):
                pass

        self.active_run_id = run_id
        self.active_log_path = log_path
        self.process_done = asyncio.Event()
        self.process_outcome = {"status": "running", "error": None}
        await self.publish({
            "stream_version": "1.0",
            "type": "control",
            "control": "run_started",
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.tail_task = asyncio.create_task(self._tail_jsonl(run_id, log_path))

    async def mark_process_done(
        self, run_id: str, status: str, error: Optional[str] = None
    ) -> None:
        if run_id != self.active_run_id or self.process_done is None:
            return
        self.process_outcome = {"status": status, "error": error}
        self.process_done.set()

    async def _tail_jsonl(self, run_id: str, log_path: Path) -> None:
        offset = 0
        pending = b""
        idle_after_done = 0

        try:
            while run_id == self.active_run_id:
                chunk = b""
                if log_path.exists():
                    try:
                        with log_path.open("rb") as handle:
                            handle.seek(offset)
                            chunk = handle.read()
                    except OSError:
                        chunk = b""

                if chunk:
                    offset += len(chunk)
                    pending += chunk
                    idle_after_done = 0
                    lines = pending.split(b"\n")
                    pending = lines.pop()
                    for raw_line in lines:
                        if not raw_line.strip():
                            continue
                        try:
                            event = json.loads(raw_line.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                            print(f"[VISUALIZER] Skipping malformed JSONL event: {exc}", flush=True)
                            continue
                        await self.publish({
                            "stream_version": "1.0",
                            "type": "event",
                            "run_id": run_id,
                            "event": event,
                        })
                elif self.process_done and self.process_done.is_set():
                    idle_after_done += 1
                    if idle_after_done >= 5:
                        break

                await asyncio.sleep(0.1)

            if pending.strip():
                try:
                    event = json.loads(pending.decode("utf-8"))
                    await self.publish({
                        "stream_version": "1.0",
                        "type": "event",
                        "run_id": run_id,
                        "event": event,
                    })
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass

            outcome = self.process_outcome or {"status": "done", "error": None}
            control = "run_completed" if outcome.get("status") == "done" else "run_failed"
            await self.publish({
                "stream_version": "1.0",
                "type": "control",
                "control": control,
                "run_id": run_id,
                "status": outcome.get("status"),
                "error": outcome.get("error"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except asyncio.CancelledError:
            raise
