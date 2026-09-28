"""
Parsing helpers: URLs out of Excel cells, Shortlister report workbooks, the
consolidated decision-maker table, Hunter domain lookups and location extraction.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import openpyxl

from leadgen import config
from leadgen.api.state import shortlister_state
from leadgen.core.clients.hunter import get_hunter_api_key


# ── URL helpers ────────────────────────────────────────────────────────────────

def extract_url(cell_or_val) -> str:
    """Extract a plain URL from an openpyxl Cell, HYPERLINK formula, or URL string."""
    if cell_or_val is None:
        return ""

    # Check openpyxl Cell hyperlink attribute first
    if hasattr(cell_or_val, "hyperlink") and cell_or_val.hyperlink:
        target = getattr(cell_or_val.hyperlink, "target", "") or ""
        if target and ("http" in str(target).lower() or "linkedin.com" in str(target).lower()):
            val = str(target).strip()
            if not val.startswith("http://") and not val.startswith("https://"):
                val = "https://" + val.lstrip("/")
            return val

    # Get cell value if Cell object
    val_raw = cell_or_val.value if hasattr(cell_or_val, "value") else cell_or_val
    if not val_raw:
        return ""

    s = str(val_raw).strip()

    # Parse =HYPERLINK("url", "label") formula
    if s.startswith("="):
        m = re.search(r'HYPERLINK\(\s*["\']([^"\']+)["\']', s, re.IGNORECASE)
        if m:
            s = m.group(1).strip()

    if s.lower() in ("not available", "n/a", "not found", "none", "—", ""):
        return ""

    # Ensure http prefix if domain or linkedin URL
    if "linkedin.com" in s.lower() or "http" in s.lower() or s.startswith("www."):
        if not s.startswith("http://") and not s.startswith("https://"):
            s = "https://" + s.lstrip("/")
        return s

    return ""


def extract_domain_from_url(url: str) -> str:
    """Extract bare domain (e.g. 'acmecorp.com') from a full URL or domain string."""
    if not url:
        return ""
    url = url.strip()
    try:
        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        host = parsed.hostname or ""
        return host.lstrip("www.")
    except Exception:
        return url.replace("https://", "").replace("http://", "").lstrip("www.").split("/")[0]


# ── Hunter.io ──────────────────────────────────────────────────────────────────

def hunter_email_count(domain: str) -> int:
    """
    Calls Hunter.io Email Count API (GET /v2/email-count).
    Returns the total email count for the domain, or 0 on error / missing domain.
    This endpoint is FREE and does NOT consume Hunter credits.
    """
    if not domain:
        return 0
    try:
        import requests as _req
        key = get_hunter_api_key()
        if not key:
            return 0
        resp = _req.get(
            "https://api.hunter.io/v2/email-count",
            params={"domain": domain, "api_key": key},
            timeout=10,
        )
        data = resp.json()
        return int(data.get("data", {}).get("total", 0))
    except Exception as exc:
        print(f"[WARN] Hunter email-count error for '{domain}': {exc}", flush=True)
        return 0


# ── Shortlister report workbooks ───────────────────────────────────────────────

def parse_shortlister_excel(path: str) -> List[Dict]:
    """Read a Shortlister report Excel and return structured company dicts."""
    companies: List[Dict] = []
    try:
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        headers = [str(c.value) if c.value else "" for c in ws[1]]
        for row in ws.iter_rows(min_row=2, values_only=False):
            if not any(c.value for c in row):
                continue
            raw = {headers[i]: row[i].value for i in range(min(len(headers), len(row)))}
            companies.append({
                "company_name": str(raw.get("Company Name", "") or ""),
                "ticker":       str(raw.get("Ticker", "") or ""),
                "industry":     str(raw.get("Industry", "") or ""),
                "revenue":      str(raw.get("Revenue (TTM)", "") or ""),
                "net_income":   str(raw.get("Net Income (TTM)", "") or ""),
                "employees":    str(raw.get("Employee Count", "") or ""),
                "location":     str(raw.get("Location", "") or ""),
                "summary":      str(raw.get("Business Summary", "") or ""),
                "website":      extract_url(raw.get("Website", "")),
                "linkedin_url": extract_url(raw.get("LinkedIn (Verified)", "")),
                "linkedin_confirmed": str(raw.get("LinkedIn Confirmed?", "") or ""),
            })
    except Exception as exc:
        print(f"[WARN] Could not parse Excel at {path}: {exc}", flush=True)
    return companies


def get_current_session_consolidated_excel() -> Optional[Path]:
    """Find the consolidated Excel report generated in the active/latest session."""
    # 1. Check if shortlister_state has last_excel recorded
    if shortlister_state.last_excel:
        p = Path(shortlister_state.last_excel)
        if p.exists() and "consolidated" in p.name.lower():
            return p
        matched = [
            f for f in config.SHORTLISTER_OUTPUT_DIR.glob("report_consolidated_*.xlsx")
            if not f.name.startswith("~$")
        ]
        if matched:
            return max(matched, key=lambda f: f.stat().st_mtime)

    # 2. Fallback: newest report_consolidated_*.xlsx in the shortlister output dir
    candidates = [
        f for f in config.SHORTLISTER_OUTPUT_DIR.glob("report_consolidated_*.xlsx")
        if not f.name.startswith("~$")
    ]
    if candidates:
        return max(candidates, key=lambda f: f.stat().st_mtime)

    return None


def get_all_decision_makers() -> List[Dict]:
    """
    Parse decision makers strictly from the Consolidated Excel file generated
    in the active/latest session. Supports both collapsible grouped layout and
    legacy flat layout. Cross-references with LinkedIn Agent outputs.
    """
    latest_excel = get_current_session_consolidated_excel()
    dm_map: Dict[tuple, Dict] = {}

    if latest_excel and latest_excel.exists():
        try:
            wb = openpyxl.load_workbook(str(latest_excel), data_only=False)
            if "Decision Maker Contacts" in wb.sheetnames:
                ws = wb["Decision Maker Contacts"]

                # Determine format: Check if row 1 is flat header or collapsible header
                is_flat_header = False
                if ws.max_row >= 1:
                    row1_vals = [str(c.value or "").strip() for c in ws[1]]
                    if "Company Name" in row1_vals and "Decision Maker Name" in row1_vals:
                        is_flat_header = True

                if is_flat_header:
                    headers = [str(c.value or "").strip() for c in ws[1]]
                    col_map = {h: i for i, h in enumerate(headers)}
                    for row in ws.iter_rows(min_row=2, values_only=False):
                        if not any(c.value for c in row):
                            continue
                        c_n = str(row[col_map.get("Company Name", 0)].value or "").strip() if "Company Name" in col_map else ""
                        c_w = extract_url(row[col_map.get("Company Website", 1)].value) if "Company Website" in col_map else ""
                        c_l = extract_url(row[col_map.get("Company LinkedIn", 2)].value) if "Company LinkedIn" in col_map else ""
                        l_c = str(row[col_map.get("Location", 3)].value or "").strip() if "Location" in col_map else ""
                        p_s = str(row[col_map.get("Decision Maker Position", 4)].value or "").strip() if "Decision Maker Position" in col_map else ""
                        d_n = str(row[col_map.get("Decision Maker Name", 5)].value or "").strip() if "Decision Maker Name" in col_map else ""
                        d_l = extract_url(row[col_map.get("Decision Maker LinkedIn", 6)].value) if "Decision Maker LinkedIn" in col_map else ""

                        if d_n and d_n not in ("—", "N/A", "None", ""):
                            key = (c_n.lower(), d_n.lower())
                            if key not in dm_map:
                                dm_map[key] = {
                                    "company_name": c_n,
                                    "company_website": c_w,
                                    "company_linkedin": c_l,
                                    "location": l_c,
                                    "name": d_n,
                                    "position": p_s,
                                    "linkedin_url": d_l,
                                    "source_file": latest_excel.name
                                }
                else:
                    # Collapsible grouped layout parser
                    current_company = ""
                    for row in ws.iter_rows(min_row=1, values_only=False):
                        row_cells = [c for c in row]
                        row_vals = [str(c.value or "").strip() for c in row_cells]
                        if not any(row_vals):
                            continue

                        val0 = row_vals[0]

                        # 1. Company Banner Row (e.g. "▸ Reliance Industries  (5 contacts)")
                        if val0.startswith("▸") or "contacts)" in val0.lower():
                            m = re.search(r'▸\s*(.*?)\s*\(\d+\s*contacts\)', val0, re.IGNORECASE)
                            if m:
                                current_company = m.group(1).strip()
                            else:
                                current_company = val0.lstrip("▸").strip().split("(")[0].strip()
                            continue

                        # 2. Sub-header row
                        if val0 in ("#", "Company Name") or "LinkedIn" in str(row_vals[3] if len(row_vals) > 3 else ""):
                            continue

                        # 3. Data row: [# (digit), Name, Position, LinkedIn (Person), Company LinkedIn, Location]
                        if val0.isdigit() or (isinstance(row_cells[0].value, (int, float)) and int(row_cells[0].value) > 0):
                            dm_name = row_vals[1] if len(row_vals) > 1 else ""
                            pos = row_vals[2] if len(row_vals) > 2 else ""
                            dm_li = extract_url(row_cells[3]) if len(row_cells) > 3 else ""
                            co_li = extract_url(row_cells[4]) if len(row_cells) > 4 else ""
                            loc = row_vals[5] if len(row_vals) > 5 else ""

                            if dm_name and dm_name not in ("—", "N/A", "None", ""):
                                key = (current_company.lower(), dm_name.lower())
                                if key not in dm_map:
                                    dm_map[key] = {
                                        "company_name": current_company,
                                        "company_website": "",
                                        "company_linkedin": co_li,
                                        "location": loc,
                                        "name": dm_name,
                                        "position": pos,
                                        "linkedin_url": dm_li,
                                        "source_file": latest_excel.name
                                    }
        except Exception as exc:
            print(f"[WARN] Error reading session Consolidated Excel {latest_excel.name}: {exc}", flush=True)

    # JSON fallback if dm_map is empty
    if not dm_map:
        json_candidates = []
        for report_dir in (config.SHORTLISTER_OUTPUT_DIR, config.SHORTLISTER_REPORTS_DIR):
            if report_dir.exists():
                json_candidates.extend(
                    f for f in report_dir.glob("report_*.json") if not f.name.startswith("~$")
                )
        if json_candidates:
            latest_json = max(json_candidates, key=lambda f: f.stat().st_mtime)
            try:
                with open(latest_json, "r", encoding="utf-8") as f:
                    jdata = json.load(f)
                    for comp in jdata.get("companies", []):
                        c_n = comp.get("name", "") or comp.get("company_name", "")
                        c_w = comp.get("website", "") or comp.get("company_website", "")
                        c_l = comp.get("linkedin_verified", "") or comp.get("company_linkedin", "")
                        l_c = comp.get("location", "")
                        for dm in comp.get("decision_makers", []):
                            d_n = dm.get("name", "")
                            p_s = dm.get("position") or dm.get("title") or ""
                            d_l = dm.get("linkedin_url") or dm.get("profile_url") or ""
                            if d_n and d_n not in ("—", "N/A", "None", ""):
                                k = (c_n.lower(), d_n.lower())
                                if k not in dm_map:
                                    dm_map[k] = {
                                        "company_name": c_n,
                                        "company_website": c_w,
                                        "company_linkedin": c_l,
                                        "location": l_c,
                                        "name": d_n,
                                        "position": p_s,
                                        "linkedin_url": d_l,
                                        "source_file": latest_json.name
                                    }
            except Exception as exc:
                print(f"[WARN] Error reading JSON report {latest_json.name}: {exc}", flush=True)

    # Cross-reference with the LinkedIn Finder outputs to populate any missing LinkedIn URLs
    linkedin_dir = config.LINKEDIN_OUTPUT_DIR
    if linkedin_dir.exists():
        for ef in linkedin_dir.glob("contacts_*.xlsx"):
            if ef.name.startswith("~$"):
                continue
            try:
                wb_link = openpyxl.load_workbook(str(ef), data_only=False)
                ws_link = wb_link.active
                headers_link = [str(c.value or "").strip() for c in ws_link[1]]
                col_map_link = {h: i for i, h in enumerate(headers_link)}
                for row in ws_link.iter_rows(min_row=2, values_only=False):
                    c_n = str(row[col_map_link.get("Company Name", 0)].value or "").strip() if "Company Name" in col_map_link else ""
                    d_n = str(row[col_map_link.get("Decision Maker Name", 5)].value or "").strip() if "Decision Maker Name" in col_map_link else ""
                    d_li = extract_url(row[col_map_link.get("Decision Maker LinkedIn", 6)].value) if "Decision Maker LinkedIn" in col_map_link else ""
                    key = (c_n.lower(), d_n.lower())
                    if key in dm_map and not dm_map[key]["linkedin_url"] and d_li:
                        dm_map[key]["linkedin_url"] = d_li
            except Exception:
                pass

    dms: List[Dict] = []
    for idx, item in enumerate(dm_map.values(), 1):
        item["id"] = f"dm-{idx}"
        dms.append(item)

    return dms


# ── Query helpers ──────────────────────────────────────────────────────────────

async def extract_location_from_query(query: str) -> str:
    """Extract location string from user's Shortlister query."""
    if not query or not query.strip():
        return "India"

    q_lower = query.lower()
    if "indian" in q_lower or "india" in q_lower:
        return "India"
    if "us" in q_lower or "united states" in q_lower or "american" in q_lower:
        return "United States"
    if "uk" in q_lower or "united kingdom" in q_lower or "british" in q_lower:
        return "United Kingdom"
    if "canada" in q_lower or "canadian" in q_lower:
        return "Canada"
    if "germany" in q_lower or "german" in q_lower:
        return "Germany"

    # LLM extraction fallback using the configured OpenAI-compatible endpoint
    try:
        from langchain_openai import ChatOpenAI
        base_url = config.OPENAI_BASE_URL
        key = config.OPENAI_API_KEY
        model = config.OPENAI_MODEL
        if base_url and key and model:
            llm = ChatOpenAI(
                base_url=base_url,
                api_key=key,
                model=model,
                temperature=0.0,
                max_tokens=30,
            )
            prompt = (
                f"Extract the primary location or country requested in this query. "
                f"If no specific location is mentioned, return 'India'. "
                f"Return ONLY the location string (e.g. 'India', 'United States'). Query: '{query}'"
            )
            res = await llm.ainvoke(prompt)
            loc = str(res.content).strip().strip('"').strip("'")
            if loc:
                return loc
    except Exception as exc:
        print(f"[WARN] Location extraction error: {exc}", flush=True)

    return "India"
