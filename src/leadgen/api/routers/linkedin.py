"""LinkedIn Finder endpoints: /linkedin/*"""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from leadgen import config
from leadgen.api.parsers import get_all_decision_makers
from leadgen.api.runner import make_sse_generator, run_linkedin_bg
from leadgen.api.schemas import LinkedInRequest
from leadgen.api.state import linkedin_state

router = APIRouter(tags=["linkedin"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("/linkedin/run")
async def run_linkedin(req: LinkedInRequest, background_tasks: BackgroundTasks):
    if linkedin_state.status == "running":
        raise HTTPException(409, "LinkedIn Finder is already running")
    linkedin_state.reset()
    companies_dicts = [c.model_dump() for c in req.companies]
    background_tasks.add_task(run_linkedin_bg, companies_dicts, req.concurrency)
    return {"status": "started", "concurrency": req.concurrency}


@router.get("/linkedin/stream")
async def linkedin_stream(request: Request):
    return EventSourceResponse(make_sse_generator(linkedin_state, request)())


@router.get("/linkedin/status")
async def linkedin_status():
    return {
        "status": linkedin_state.status,
        "current_company": linkedin_state.current_company,
        "active_companies": linkedin_state.active_companies,
        "completed_count": linkedin_state.completed_count,
        "total_count": linkedin_state.total_count,
        "error": linkedin_state.error,
    }


@router.get("/linkedin/files")
async def linkedin_files():
    """List all available company Excel files in the LinkedIn output directory."""
    output_dir = config.LINKEDIN_OUTPUT_DIR
    if not output_dir.exists():
        return {"files": []}

    files = []
    for f in sorted(output_dir.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.name.startswith("~$"):
            continue
        files.append({
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "mtime": f.stat().st_mtime,
            "download_url": f"/linkedin/download/{f.name}"
        })
    return {"files": files}


@router.get("/linkedin/download/{filename}")
async def linkedin_download_file(filename: str):
    """Download a specific company Excel report."""
    safe_name = Path(filename).name
    file_path = config.LINKEDIN_OUTPUT_DIR / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, f"File '{safe_name}' not found")
    return FileResponse(str(file_path), media_type=XLSX_MEDIA_TYPE, filename=safe_name)


@router.get("/linkedin/decision-makers")
async def get_decision_makers():
    """Retrieve all parsed decision makers across all companies processed so far."""
    dms = get_all_decision_makers()
    return {"decision_makers": dms, "total": len(dms)}
