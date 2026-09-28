"""Consolidated export endpoints and the global reset: /export/*, /reset"""

import asyncio
import io
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from leadgen import config
from leadgen.api.parsers import get_all_decision_makers
from leadgen.api.state import _email_store, linkedin_state, shortlister_state
from leadgen.core.exporters.builder import build_export_xlsx

router = APIRouter(tags=["exports"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/export/consolidated")
async def export_consolidated():
    """
    Generate and download the 2-sheet consolidated Excel report:
      Sheet 1 — Company Overview
      Sheet 2 — Decision Makers (PivotTable or grouped table)
    Also saves a copy to the exports directory.
    """
    companies = shortlister_state.companies or []
    location = shortlister_state.extracted_location or "India"
    dms = get_all_decision_makers()

    try:
        xlsx_bytes = await asyncio.to_thread(
            build_export_xlsx, companies, location, dms, dict(_email_store)
        )
    except Exception as exc:
        raise HTTPException(500, f"Export generation failed: {exc}")

    # Save a copy to disk
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"export_{timestamp}.xlsx"
    disk_path = config.EXPORTS_DIR / filename
    try:
        disk_path.write_bytes(xlsx_bytes)
        print(f"[EXPORT] Saved to {disk_path}", flush=True)
    except Exception as save_exc:
        print(f"[WARN] Could not save export to disk: {save_exc}", flush=True)

    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/list")
async def list_exports():
    """List all previously exported Excel files."""
    exports_dir = config.EXPORTS_DIR
    if not exports_dir.exists():
        return {"files": []}
    files = [
        {
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "mtime": f.stat().st_mtime,
            "download_url": f"/export/download/{f.name}",
        }
        for f in sorted(exports_dir.glob("export_*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not f.name.startswith("~$")
    ]
    return {"files": files}


@router.get("/export/download/{filename}")
async def download_export(filename: str):
    """Re-download a previously generated export file."""
    safe = Path(filename).name
    path = config.EXPORTS_DIR / safe
    if not path.exists():
        raise HTTPException(404, f"Export '{safe}' not found")
    return FileResponse(str(path), media_type=XLSX_MEDIA_TYPE, filename=safe)


@router.post("/reset")
async def reset_all():
    """Reset both agent states (does not kill running processes)."""
    shortlister_state.reset()
    linkedin_state.reset()
    return {"status": "reset"}
