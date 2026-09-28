"""Shortlister endpoints: /shortlister/*"""

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from leadgen import config
from leadgen.api.runner import make_sse_generator, run_shortlister_bg
from leadgen.api.schemas import ShortlisterRequest
from leadgen.api.state import shortlister_state, visualizer_broker

router = APIRouter(tags=["shortlister"])


@router.post("/shortlister/run")
async def run_shortlister(req: ShortlisterRequest, background_tasks: BackgroundTasks):
    if shortlister_state.status == "running":
        raise HTTPException(409, "Shortlister is already running")
    shortlister_state.reset()
    run_id = f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    log_path = config.LOGS_DIR / f"run_{run_id}.jsonl"
    await visualizer_broker.begin_run(run_id, log_path)
    background_tasks.add_task(run_shortlister_bg, req.query, run_id)
    return {"status": "started", "run_id": run_id}


@router.get("/shortlister/stream")
async def shortlister_stream(request: Request):
    return EventSourceResponse(make_sse_generator(shortlister_state, request)())


@router.get("/shortlister/status")
async def shortlister_status():
    return {
        "status": shortlister_state.status,
        "excel_path": shortlister_state.last_excel,
        "companies": shortlister_state.companies,
        "error": shortlister_state.error,
    }


@router.get("/shortlister/download")
async def shortlister_download():
    path = shortlister_state.last_excel
    if not path or not Path(path).exists():
        raise HTTPException(404, "No Excel file available yet")
    p = Path(path)
    return FileResponse(
        str(p),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=p.name,
    )
