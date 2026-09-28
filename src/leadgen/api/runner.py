"""
Background runners.

Each agent runs as a subprocess launched through its package entry point
(``python -m leadgen.agents.*``) with the repo root as cwd. Stdout/stderr is teed
to the terminal and to every connected browser (SSE queues + WebSocket clients).
"""

import asyncio
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import Request

from leadgen import config
from leadgen.api.parsers import extract_location_from_query, parse_shortlister_excel
from leadgen.api.state import (
    AgentState,
    linkedin_state,
    shortlister_state,
    visualizer_broker,
    ws_log_clients,
)

SHORTLISTER_MODULE = "leadgen.agents.shortlister"
LINKEDIN_MODULE = "leadgen.agents.linkedin_finder"


async def broadcast(state: AgentState, line: str) -> None:
    """Buffer line and push to all live SSE subscriber queues (plus WebSocket clients)."""
    state.log_buffer.append(line)
    dead: List[asyncio.Queue] = []
    for q in list(state.log_queues):
        try:
            q.put_nowait(line)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        if q in state.log_queues:
            state.log_queues.remove(q)

    # Also fan-out plain text logs to WS clients as a 'log' envelope
    ws_envelope = json.dumps({"event_type": "log", "data": {"message": line}})
    dead_ws = []
    for ws in list(ws_log_clients):
        try:
            await ws.send_text(ws_envelope)
        except Exception:
            dead_ws.append(ws)
    for ws in dead_ws:
        if ws in ws_log_clients:
            ws_log_clients.remove(ws)


async def send_sentinel(state: AgentState) -> None:
    """Signal all SSE queues that the stream has ended."""
    for q in list(state.log_queues):
        try:
            q.put_nowait(None)
        except Exception:
            pass


async def stream_subprocess(
    state: AgentState,
    cmd: List[str],
    cwd: Path,
    stdin_input: Optional[str] = None,
    prefix: Optional[str] = None,
    env_overrides: Optional[Dict[str, str]] = None,
) -> int:
    """
    Run a subprocess, tee its stdout+stderr to:
      1. The real terminal (unchanged, via print())
      2. All SSE subscriber queues (via broadcast)

    Uses a reader thread + non-blocking queue poll to keep the asyncio
    event loop free on Windows where ProactorEventLoop subprocesses can
    behave inconsistently.
    """
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"  # force line-flushed output from subprocesses
    if env_overrides:
        env.update(env_overrides)

    line_q: "queue.Queue[Optional[str]]" = queue.Queue()

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if stdin_input is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    if stdin_input is not None:
        try:
            proc.stdin.write(stdin_input)
            proc.stdin.close()
        except Exception:
            pass

    def _reader():
        try:
            for raw_line in proc.stdout:
                line_q.put(raw_line.rstrip("\n"))
        finally:
            proc.wait()
            line_q.put(None)  # sentinel

    threading.Thread(target=_reader, daemon=True).start()

    while True:
        try:
            item = line_q.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.02)
            continue

        if item is None:
            break

        formatted_item = f"[{prefix}] {item}" if prefix else item

        # Tee to terminal
        print(formatted_item, flush=True)
        # Broadcast to browser
        await broadcast(state, formatted_item)

    return proc.returncode


def newest_shortlister_report() -> Optional[Path]:
    """Newest consolidated report in the shortlister output dir, else the newest report."""
    output_dir = config.SHORTLISTER_OUTPUT_DIR
    if not output_dir.exists():
        return None

    def _workbooks(pattern: str) -> List[Path]:
        return [f for f in output_dir.glob(pattern) if not f.name.startswith("~$")]

    candidates = _workbooks("report_consolidated_*.xlsx") or _workbooks("report_*.xlsx")
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


# ── Shortlister Background Task ────────────────────────────────────────────────

async def run_shortlister_bg(query: str, run_id: str) -> None:
    state = shortlister_state
    state.status = "running"
    state.error = None
    state.user_query = query
    state.extracted_location = await extract_location_from_query(query)
    await broadcast(state, f"📍 Extracted target location from query: '{state.extracted_location}'")

    try:
        rc = await stream_subprocess(
            state,
            [sys.executable, "-u", "-m", SHORTLISTER_MODULE, query],
            config.ROOT_DIR,
            env_overrides={"PIPELINE_RUN_ID": run_id},
        )

        # The agent writes straight into the served output dir, so just pick up the result
        newest = newest_shortlister_report()
        if newest:
            state.last_excel = str(newest)
            state.companies = parse_shortlister_excel(str(newest))

        state.status = "done" if rc == 0 else "error"
        if rc != 0:
            state.error = f"Process exited with code {rc}"

    except Exception as exc:
        state.status = "error"
        state.error = str(exc)
        await broadcast(state, f"[ERROR] {exc}")
    finally:
        await send_sentinel(state)
        await visualizer_broker.mark_process_done(run_id, state.status, state.error)


# ── LinkedIn Finder Background Task ───────────────────────────────────────────

async def run_linkedin_bg(companies: list, concurrency: int = 10) -> None:
    state = linkedin_state
    state.status = "running"
    state.error = None
    state.total_count = len(companies)
    state.completed_count = 0
    state.active_companies = []

    sem = asyncio.Semaphore(max(1, concurrency))
    lock = asyncio.Lock()
    failed_companies: List[str] = []

    await broadcast(state, f"🚀 Starting parallel extraction for {len(companies)} companies with concurrency limit = {concurrency}")

    async def _worker(company: dict):
        company_name = company["company_name"]
        linkedin_url = company.get("linkedin_url", "")
        website = company.get("website", "")
        target_location = company.get("location") or shortlister_state.extracted_location or "India"

        async with sem:
            async with lock:
                state.active_companies.append(company_name)
                state.current_company = ", ".join(state.active_companies)

            separator = f"{'─' * 60}"
            await broadcast(state, f"[{company_name}] {separator}")
            await broadcast(state, f"[{company_name}]   Processing: {company_name} (Location: {target_location})")
            await broadcast(state, f"[{company_name}] {separator}")

            cmd = [
                sys.executable, "-u", "-m", LINKEDIN_MODULE,
                "--company_name", company_name,
                "--company_website", website or "",
                "--location", target_location or "India",
            ]
            if linkedin_url and linkedin_url != "NOT FOUND":
                cmd.extend(["--company_linkedin", linkedin_url])

            try:
                rc = await stream_subprocess(
                    state,
                    cmd,
                    config.ROOT_DIR,
                    prefix=company_name,
                )

                if rc != 0:
                    async with lock:
                        failed_companies.append(f"'{company_name}' (exit code {rc})")
                    await broadcast(state, f"[{company_name}] ❌ Exited with code {rc}")
                else:
                    await broadcast(state, f"[{company_name}] ✅ Completed successfully")

            except Exception as exc:
                async with lock:
                    failed_companies.append(f"'{company_name}' ({exc})")
                await broadcast(state, f"[{company_name}] ❌ Error: {exc}")
            finally:
                async with lock:
                    if company_name in state.active_companies:
                        state.active_companies.remove(company_name)
                    state.completed_count += 1
                    state.current_company = ", ".join(state.active_companies) if state.active_companies else None

    tasks = [_worker(comp) for comp in companies]
    await asyncio.gather(*tasks, return_exceptions=True)

    if failed_companies:
        state.status = "error" if len(failed_companies) == len(companies) else "done"
        state.error = f"Completed with errors in {len(failed_companies)} company(ies): {', '.join(failed_companies)}"
    else:
        state.status = "done"

    state.active_companies.clear()
    state.current_company = None
    await send_sentinel(state)


# ── Generic SSE Generator ──────────────────────────────────────────────────────

def make_sse_generator(state: AgentState, request: Request):
    async def generator():
        # Replay buffered lines for reconnecting clients
        for line in list(state.log_buffer):
            yield {"event": "log", "data": line}

        # If already finished, send done and exit immediately
        if state.status not in ("idle", "running"):
            yield {"event": "done", "data": state.status}
            return

        # If still idle (run not started), nothing to stream
        if state.status == "idle":
            return

        # Subscribe to live updates
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        state.log_queues.append(q)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=15.0)
                    if item is None:
                        yield {"event": "done", "data": state.status}
                        break
                    yield {"event": "log", "data": item}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            if q in state.log_queues:
                state.log_queues.remove(q)

    return generator
