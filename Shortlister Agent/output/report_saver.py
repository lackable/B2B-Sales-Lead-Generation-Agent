import os
import json
import traceback
from datetime import datetime
import config
from output.excel_exporter import export_excel
from output.consolidated_exporter import export_consolidated_excel

def save_all(
    verified_companies: list,
    screener_query: dict = None,
    session_id: str = "session"
) -> dict:
    """Master function to save final shortlister report files (JSON & Excel)."""
    try:
        os.makedirs(config.EXCEL_OUTPUT_DIR, exist_ok=True)
        os.makedirs(config.REPORTS_OUTPUT_DIR, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_session = str(session_id).replace("/", "_").replace("\\", "_")
        base_filename = f"report_{timestamp}_{safe_session}"
        
        # 1. Save standard Shortlist Excel report
        excel_path = export_excel(verified_companies, timestamp)
        
        # 2. Save 2-Tab Consolidated Excel report (Shortlist + Decision Makers)
        consolidated_excel_path = export_consolidated_excel(verified_companies, timestamp)
        
        # 3. Save JSON report
        json_path = os.path.join(config.REPORTS_OUTPUT_DIR, f"{base_filename}.json")
        json_data = {
            "session_id": session_id,
            "timestamp": timestamp,
            "screener_query": screener_query or {},
            "total_companies": len(verified_companies),
            "companies": verified_companies
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
            
        return {
            "timestamp": timestamp,
            "excel": consolidated_excel_path,
            "shortlist_excel": excel_path,
            "json": json_path
        }
    except Exception as e:
        print(f"[ERROR] Exception in save_all: {e}\n{traceback.format_exc()}")
        return {"error": str(e)}
