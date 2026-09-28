"""
Export Builder — Consolidated Excel Export Generator
=====================================================
Builds a 2-sheet .xlsx:
  Sheet 1 — "Company Overview"   : one row per shortlisted company
  Hidden  — "_dm_data"           : raw DM table (data source for PivotTable)
  Sheet 2 — "Decision Makers"    : native Excel PivotTable (fallback: styled grouped table)
"""

import io
from datetime import datetime
from itertools import groupby
from typing import Dict, List, Tuple

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import Outline
from openpyxl.worksheet.table import Table, TableStyleInfo as WsTableStyleInfo


# ── Shared Style Constants ─────────────────────────────────────────────────────

def _side():
    return Side(style="thin", color="D1D5DB")


def _border():
    s = _side()
    return Border(left=s, right=s, top=s, bottom=s)


HDR_FILL   = PatternFill("solid", fgColor="1E3A5F")
HDR_FONT   = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
HDR_ALIGN  = Alignment(horizontal="center", vertical="center", wrap_text=True)
LINK_FONT  = Font(color="1D4ED8", underline="single", name="Calibri", size=10)
BODY_FONT  = Font(name="Calibri", size=10)
BOLD_FONT  = Font(bold=True, name="Calibri", size=10)
TITLE_FONT = Font(bold=True, size=13, name="Calibri", color="1E3A5F")
META_FONT  = Font(italic=True, size=9,  name="Calibri", color="6B7280")

S1_ALT_FILLS = [
    PatternFill("solid", fgColor="EFF6FF"),
    PatternFill("solid", fgColor="FFFFFF"),
]

COMPANY_FILLS = [
    PatternFill("solid", fgColor="EFF6FF"),
    PatternFill("solid", fgColor="F0FDF4"),
    PatternFill("solid", fgColor="FEF9C3"),
    PatternFill("solid", fgColor="FDF2F8"),
    PatternFill("solid", fgColor="F3F4F6"),
    PatternFill("solid", fgColor="FFF7ED"),
]


def _set_header_row(ws, headers: List[str], row: int = 1):
    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=row, column=ci, value=h)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = HDR_ALIGN
        cell.border = _border()
    ws.row_dimensions[row].height = 22


def _hyperlink_cell(cell, url: str):
    """Safely set a hyperlink on a cell; swallow if unsupported."""
    try:
        cell.hyperlink = url
    except Exception:
        pass


# ── Main Public Entry Point ────────────────────────────────────────────────────

def build_export_xlsx(
    companies: List[dict],
    location: str,
    dms: List[dict],
    email_store: Dict[Tuple[str, str], str],
) -> bytes:
    """
    Build and return the consolidated export workbook as raw bytes.

    :param companies:    List of company dicts (from shortlister_state.companies)
    :param location:     Extracted query location string  (e.g. "India")
    :param dms:          List of DM dicts (from _get_all_decision_makers())
    :param email_store:  {(company_name_lower, dm_name_lower): email_str}
    :returns:            .xlsx bytes ready to be served or written to disk
    """
    wb = Workbook()

    # ── Sheet 1: Company Overview ──────────────────────────────────────────────
    _build_company_overview_sheet(wb, companies, location)

    # ── Hidden data sheet: _dm_data ───────────────────────────────────────────
    dms_sorted = sorted(dms, key=lambda d: d.get("company_name", "").lower())
    table_ref, last_data_row = _build_dm_data_sheet(wb, dms_sorted, email_store)

    # ── Sheet 2: Decision Makers ───────────────────────────────────────────────
    ws2 = wb.create_sheet("Decision Makers")
    DM_HEADERS = ["Company Name", "Decision Maker Name", "Position", "Decision Maker LinkedIn", "Email", "Phone"]

    # Always write the styled grouped table so all data rows are immediately visible in Excel
    _write_grouped_table(ws2, dms_sorted, DM_HEADERS, email_store)


    # ── Serialise ──────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ── Sheet Builders ─────────────────────────────────────────────────────────────

def _build_company_overview_sheet(wb: Workbook, companies: List[dict], location: str):
    """Write Sheet 1 — Company Overview."""
    ws1 = wb.active
    ws1.title = "Company Overview"

    headers = [
        "Company Name", "Industry", "Revenue", "Location",
        "Company Website", "Company Description", "Employee Count", "Company LinkedIn",
    ]
    _set_header_row(ws1, headers)
    ws1.freeze_panes = "A2"

    for ri, comp in enumerate(companies, 2):
        fill = S1_ALT_FILLS[ri % 2]

        def _c(ci, val, is_link=False, wrap=False):
            cell = ws1.cell(row=ri, column=ci, value=val)
            cell.fill = fill
            cell.font = LINK_FONT if is_link else BODY_FONT
            cell.alignment = Alignment(vertical="top", wrap_text=wrap)
            cell.border = _border()
            return cell

        _c(1, comp.get("company_name", ""))
        _c(2, comp.get("industry", ""))
        _c(3, comp.get("revenue", ""))
        comp_loc = comp.get("location", "") or location
        _c(4, comp_loc)

        website = (comp.get("website", "") or "").strip()
        if website and website not in ("NOT FOUND", "N/A", ""):
            c = _c(5, website, is_link=True)
            _hyperlink_cell(c, website)
        else:
            _c(5, website or "")

        summary = (comp.get("summary", "") or "")
        # Truncate very long summaries to avoid oversized cells
        _c(6, summary[:800] if len(summary) > 800 else summary, wrap=True)

        _c(7, comp.get("employees", ""))

        linkedin = (comp.get("linkedin_url", "") or "").strip()
        if linkedin and linkedin not in ("NOT FOUND", "N/A", ""):
            c = _c(8, linkedin, is_link=True)
            _hyperlink_cell(c, linkedin)
        else:
            _c(8, linkedin or "")

    # Column widths
    for ci, w in enumerate([25, 22, 16, 14, 32, 60, 14, 36], 1):
        ws1.column_dimensions[get_column_letter(ci)].width = w


def _build_dm_data_sheet(
    wb: Workbook,
    dms_sorted: List[dict],
    email_store: Dict[Tuple[str, str], str],
) -> Tuple[str, int]:
    """
    Write the hidden _dm_data sheet that serves as the PivotTable data source.
    Returns (table_ref, last_data_row).
    """
    ws = wb.create_sheet("_dm_data")
    ws.sheet_state = "hidden"

    dm_headers = ["Company Name", "DM Name", "Position", "DM LinkedIn", "Email", "Phone"]
    for ci, h in enumerate(dm_headers, 1):
        ws.cell(row=1, column=ci, value=h)

    for ri, dm in enumerate(dms_sorted, 2):
        c_name = dm.get("company_name", "")
        d_name = dm.get("name", "")
        key    = (c_name.strip().lower(), d_name.strip().lower())
        email  = email_store.get(key, "")

        dm_li = (
            dm.get("linkedin_url")
            or dm.get("linkedin")
            or dm.get("profile_url")
            or dm.get("person_linkedin")
            or dm.get("dm_linkedin")
            or ""
        )
        ws.cell(row=ri, column=1, value=c_name)
        ws.cell(row=ri, column=2, value=d_name)
        ws.cell(row=ri, column=3, value=dm.get("position", ""))
        ws.cell(row=ri, column=4, value=dm_li)
        ws.cell(row=ri, column=5, value=email)
        ws.cell(row=ri, column=6, value="")  # Phone — always blank

    last_data_row = max(len(dms_sorted) + 1, 2)
    table_ref = f"A1:{get_column_letter(6)}{last_data_row}"

    t = Table(displayName="dm_source_table", ref=table_ref)
    t.tableStyleInfo = WsTableStyleInfo(name="TableStyleMedium9", showRowStripes=True)
    ws.add_table(t)

    return table_ref, last_data_row


# ── PivotTable Builder ─────────────────────────────────────────────────────────

def _try_create_pivot(
    wb: Workbook,
    ws2,
    dms_sorted: List[dict],
    dm_headers: List[str],
    table_ref: str,
    last_data_row: int,
    email_store: Dict[Tuple[str, str], str],
) -> bool:
    """
    Attempt to build a native Excel PivotTable on ws2 backed by _dm_data.
    All 6 fields are row fields (tabular layout) so the result looks like a
    grouped report with Company Name as the outer row grouping.
    Returns True on success, False on any failure.
    """
    try:
        # openpyxl uses TableDefinition for the PivotTable and PivotField / RowColField
        from openpyxl.pivot.table import (  # type: ignore
            TableDefinition, PivotField, RowColField, PivotTableStyle, Location,
        )
        from openpyxl.pivot.cache import (  # type: ignore
            CacheDefinition, CacheField, CacheSource, SharedItems, WorksheetSource,
        )

        # ── Collect column values for SharedItems ──────────────────────────────
        col_vals: List[List[str]] = [[] for _ in range(6)]
        for dm in dms_sorted:
            c_name = dm.get("company_name", "")
            d_name = dm.get("name", "")
            key    = (c_name.strip().lower(), d_name.strip().lower())
            email  = email_store.get(key, "")
            dm_li = dm.get("linkedin_url") or dm.get("linkedin") or dm.get("profile_url") or dm.get("person_linkedin") or dm.get("dm_linkedin") or ""
            col_vals[0].append(c_name)
            col_vals[1].append(d_name)
            col_vals[2].append(dm.get("position", "") or "")
            col_vals[3].append(dm_li)
            col_vals[4].append(email)
            col_vals[5].append("")

        # ── Build CacheFields with SharedItems ─────────────────────────────────
        # SharedItems._fields must be a tuple (NestedSequence descriptor rejects lists)
        try:
            from openpyxl.pivot.cache import Text as _Text  # type: ignore
            def _make_text_item(v: str):
                return _Text(v=v)
        except ImportError:
            _make_text_item = None

        cache_fields: List[CacheField] = []
        for header, vals in zip(dm_headers, col_vals):
            if _make_text_item is not None:
                unique = tuple(dict.fromkeys(v for v in vals if v is not None))
                si = SharedItems(_fields=tuple(_make_text_item(v) for v in unique))
                cf = CacheField(name=header, sharedItems=si)
            else:
                cf = CacheField(name=header)
            cache_fields.append(cf)

        # ── Cache Definition ───────────────────────────────────────────────────
        # cacheFields also uses NestedSequence, so set post-construction
        ws_source  = WorksheetSource(sheet="_dm_data", ref=table_ref)
        cache_src  = CacheSource(type="worksheet", worksheetSource=ws_source)
        cache_def  = CacheDefinition(cacheSource=cache_src, invalid=False, saveData=True)
        cache_def.cacheFields = cache_fields


        # ── PivotTable (TableDefinition) ───────────────────────────────────────
        # Build minimal first; set sequence attributes post-construction because
        # openpyxl's NestedSequence descriptor rejects plain lists in __init__.
        pt_ref = f"A3:{get_column_letter(6)}{last_data_row + 4}"
        pt_loc = Location(ref=pt_ref, firstHeaderRow=1, firstDataRow=2, firstDataCol=0)

        pt = TableDefinition(name="DMPivot", cacheId=1, dataCaption="Values", location=pt_loc)
        pt.pivotFields = [
            PivotField(axis="axisRow", compact=False, outline=False, showAll=False)
            for _ in range(6)
        ]
        pt.rowFields          = [RowColField(x=i) for i in range(6)]
        pt.compact            = False
        pt.compactData        = False
        pt.outline            = False
        pt.outlineData        = False
        pt.showDrill          = True
        pt.pivotTableStyleInfo = PivotTableStyle(
            name="PivotStyleLight16",
            showRowHeaders=True,
            showColHeaders=True,
            showRowStripes=True,
        )
        pt.cache = cache_def


        # Attach PivotTable to worksheet
        ws2._pivots.append(pt)  # type: ignore[attr-defined]

        # Title + meta row above the PivotTable area
        ws2["A1"] = "Decision Makers — Grouped by Company"
        ws2["A1"].font = TITLE_FONT
        ws2["A2"] = (
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}   |   "
            "Tip: Right-click the PivotTable → Refresh to update data"
        )
        ws2["A2"].font = META_FONT

        # Column widths for readability
        for ci, w in enumerate([25, 22, 30, 35, 28, 15], 1):
            ws2.column_dimensions[get_column_letter(ci)].width = w

        return True

    except Exception as exc:
        print(
            f"[EXPORT] PivotTable creation failed "
            f"({type(exc).__name__}: {exc}). Using styled grouped table as fallback.",
            flush=True,
        )
        return False


# ── Fallback: Styled Grouped Table ────────────────────────────────────────────

def _write_grouped_table(
    ws2,
    dms_sorted: List[dict],
    dm_headers: List[str],
    email_store: Dict[Tuple[str, str], str],
):
    """
    Writes a collapsible grouped table for Decision Makers:
      • Merged company banner row (▸ Company Name (N contacts))
      • Sub-header row (#, Name, Position, Decision Maker LinkedIn, Email, Location)
      • Collapsible row groups per company
      • Clickable LinkedIn hyperlinks
    """
    ws2.sheet_properties.outlinePr = Outline(summaryBelow=False, summaryRight=False)

    FNT = "Arial"
    company_font = Font(name=FNT, bold=True, size=12, color="FFFFFF")
    company_fill = PatternFill("solid", fgColor="2F5496")
    sub_hdr_font = Font(name=FNT, bold=True, size=10, color="2F5496")
    sub_hdr_fill = PatternFill("solid", fgColor="D6E4F0")
    data_font    = Font(name=FNT, size=10)
    link_font    = Font(name=FNT, size=10, color="0563C1", underline="single")
    alt_fill     = PatternFill("solid", fgColor="F2F2F2")
    border       = Border(
        left=Side("thin", color="B4C6E7"), right=Side("thin", color="B4C6E7"),
        top=Side("thin", color="B4C6E7"),  bottom=Side("thin", color="B4C6E7"),
    )
    wrap = Alignment(vertical="center", wrap_text=True)
    ctr  = Alignment(horizontal="center", vertical="center")

    HEADERS = ["#", "Name", "Position", "LinkedIn (Person)", "Email", "Location"]
    widths = {"A": 6, "B": 28, "C": 50, "D": 45, "E": 30, "F": 18}
    for col_let, w in widths.items():
        ws2.column_dimensions[col_let].width = w

    current_row = 1

    for company_name, group_iter in groupby(dms_sorted, key=lambda d: d.get("company_name", "")):
        group_dms = list(group_iter)
        comp_loc = group_dms[0].get("location", "") if group_dms else ""

        # ── COMPANY HEADER BANNER ─────────────────────────────────
        ws2.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=6)
        hdr_cell = ws2.cell(row=current_row, column=1, value=f"  ▸ {company_name or 'Unknown Company'}  ({len(group_dms)} contacts)")
        hdr_cell.font, hdr_cell.fill, hdr_cell.alignment = company_font, company_fill, ctr
        for c in range(1, 7):
            ws2.cell(row=current_row, column=c).fill = company_fill
            ws2.cell(row=current_row, column=c).border = border
        ws2.row_dimensions[current_row].height = 28
        current_row += 1

        # ── SUB-HEADER ──────────────────────────────────────────
        first_data_row = current_row
        for ci, h in enumerate(HEADERS, 1):
            cell = ws2.cell(row=current_row, column=ci, value=h)
            cell.font, cell.fill, cell.alignment, cell.border = sub_hdr_font, sub_hdr_fill, ctr, border
        current_row += 1

        # ── CONTACT ROWS ────────────────────────────────────────
        for idx, dm in enumerate(group_dms, 1):
            d_name = dm.get("name", "")
            key = (company_name.strip().lower(), d_name.strip().lower())
            email = email_store.get(key, "") or dm.get("email", "") or dm.get("hunter_email", "")
            linkedin = (
                dm.get("linkedin_url")
                or dm.get("linkedin")
                or dm.get("profile_url")
                or dm.get("person_linkedin")
                or dm.get("dm_linkedin")
                or ""
            )
            linkedin = str(linkedin).strip() if linkedin else ""
            loc = dm.get("location") or comp_loc or ""

            # Col A: #
            c = ws2.cell(row=current_row, column=1, value=idx)
            c.font, c.border, c.alignment = data_font, border, ctr

            # Col B: Name
            c = ws2.cell(row=current_row, column=2, value=d_name)
            c.font, c.border, c.alignment = data_font, border, wrap

            # Col C: Position
            c = ws2.cell(row=current_row, column=3, value=dm.get("position", ""))
            c.font, c.border, c.alignment = data_font, border, wrap

            # Col D: LinkedIn (Person)
            if linkedin and linkedin.startswith("http"):
                label = d_name if d_name else linkedin
                safe_url = linkedin.replace('"', '%22')
                safe_label = label.replace('"', '""')
                c = ws2.cell(row=current_row, column=4, value=f'=HYPERLINK("{safe_url}", "{safe_label}")')
                _hyperlink_cell(c, linkedin)
                c.font, c.border, c.alignment = link_font, border, wrap
            else:
                c = ws2.cell(row=current_row, column=4, value="—")
                c.font, c.border, c.alignment = data_font, border, wrap

            # Col E: Email
            c = ws2.cell(row=current_row, column=5, value=email or "—")
            c.font, c.border, c.alignment = data_font, border, wrap

            # Col F: Location
            c = ws2.cell(row=current_row, column=6, value=loc or "—")
            c.font, c.border, c.alignment = data_font, border, ctr

            # Alternating fill
            if idx % 2 == 0:
                for ci in range(1, 7):
                    ws2.cell(row=current_row, column=ci).fill = alt_fill

            current_row += 1

        last_data_row = current_row - 1

        # ── GROUP (collapsible) ─────────────────────────────────
        if last_data_row >= first_data_row:
            ws2.row_dimensions.group(first_data_row, last_data_row, hidden=True)
        current_row += 1  # spacer

    ws2.sheet_view.showGridLines = False
