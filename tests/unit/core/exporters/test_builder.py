"""Unit tests for :mod:`leadgen.core.exporters.builder`."""

import io

from openpyxl import load_workbook

from leadgen.core.exporters.builder import build_export_xlsx

OVERVIEW_HEADERS = [
    "Company Name",
    "Industry",
    "Revenue",
    "Location",
    "Company Website",
    "Company Description",
    "Employee Count",
    "Company LinkedIn",
]
DM_DATA_HEADERS = ["Company Name", "DM Name", "Position", "DM LinkedIn", "Email", "Phone"]
GROUP_HEADERS = ["#", "Name", "Position", "LinkedIn (Person)", "Email", "Location"]


def _load(companies, dms, email_store=None, location="India"):
    data = build_export_xlsx(companies, location, dms, email_store or {})
    assert isinstance(data, bytes)
    assert data[:2] == b"PK"  # xlsx zip signature
    return load_workbook(io.BytesIO(data))


# ── Workbook shape ────────────────────────────────────────────────────────────

def test_sheets_and_hidden_dm_data_sheet():
    workbook = _load([{"company_name": "Acme"}], [])

    assert workbook.sheetnames == ["Company Overview", "_dm_data", "Decision Makers"]
    assert workbook["_dm_data"].sheet_state == "hidden"
    assert workbook["Company Overview"].sheet_state == "visible"
    assert workbook["Decision Makers"].sheet_state == "visible"


# ── Company Overview sheet ────────────────────────────────────────────────────

def test_company_overview_values_and_location_fallback():
    companies = [
        {
            "company_name": "Acme",
            "industry": "Software",
            "revenue": "10M",
            "location": "Bangalore",
            "website": "https://acme.com",
            "summary": "Acme summary",
            "employees": 10,
            "linkedin_url": "https://linkedin.com/company/acme",
        },
        {"company_name": "Beta", "industry": "Hardware", "revenue": "5M", "employees": 5},
    ]
    workbook = _load(companies, [], location="India")
    ws = workbook["Company Overview"]

    assert [ws.cell(row=1, column=c).value for c in range(1, 9)] == OVERVIEW_HEADERS
    assert [ws.cell(row=2, column=c).value for c in range(1, 9)] == [
        "Acme",
        "Software",
        "10M",
        "Bangalore",
        "https://acme.com",
        "Acme summary",
        10,
        "https://linkedin.com/company/acme",
    ]
    # Beta has no location -> falls back to the query-level location argument
    assert ws.cell(row=3, column=1).value == "Beta"
    assert ws.cell(row=3, column=4).value == "India"


def test_website_and_linkedin_hyperlinks_set():
    companies = [
        {
            "company_name": "Acme",
            "website": "https://acme.com",
            "linkedin_url": "https://linkedin.com/company/acme",
        }
    ]
    ws = _load(companies, [])["Company Overview"]

    assert ws.cell(row=2, column=5).value == "https://acme.com"
    assert ws.cell(row=2, column=5).hyperlink is not None
    assert ws.cell(row=2, column=5).hyperlink.target == "https://acme.com"

    assert ws.cell(row=2, column=8).value == "https://linkedin.com/company/acme"
    assert ws.cell(row=2, column=8).hyperlink is not None
    assert ws.cell(row=2, column=8).hyperlink.target == "https://linkedin.com/company/acme"


def test_placeholder_urls_are_not_hyperlinked():
    companies = [{"company_name": "Acme", "website": "NOT FOUND", "linkedin_url": "N/A"}]
    ws = _load(companies, [])["Company Overview"]

    assert ws.cell(row=2, column=5).value == "NOT FOUND"
    assert ws.cell(row=2, column=5).hyperlink is None
    assert ws.cell(row=2, column=8).value == "N/A"
    assert ws.cell(row=2, column=8).hyperlink is None


def test_business_summary_truncated_to_800_chars():
    summary = "x" * 900
    ws = _load([{"company_name": "Acme", "summary": summary}], [])["Company Overview"]

    assert ws.cell(row=2, column=6).value == "x" * 800
    assert len(ws.cell(row=2, column=6).value) == 800


def test_short_summary_is_not_truncated():
    ws = _load([{"company_name": "Acme", "summary": "short"}], [])["Company Overview"]
    assert ws.cell(row=2, column=6).value == "short"


# ── _dm_data sheet ────────────────────────────────────────────────────────────

def test_dm_data_sheet_headers_rows_and_email_lookup():
    dms = [{"company_name": "Acme", "name": "Jane Doe", "position": "CEO", "linkedin_url": "https://li/jane"}]
    email_store = {("acme", "jane doe"): "jane@acme.com"}
    ws = _load([{"company_name": "Acme"}], dms, email_store)["_dm_data"]

    assert [ws.cell(row=1, column=c).value for c in range(1, 7)] == DM_DATA_HEADERS

    row = [ws.cell(row=2, column=c).value for c in range(1, 7)]
    assert row[0] == "Acme"
    assert row[1] == "Jane Doe"
    assert row[2] == "CEO"
    assert row[3] == "https://li/jane"
    assert row[4] == "jane@acme.com"
    assert row[5] in (None, "")  # Phone always blank


def test_dm_data_email_blank_when_store_key_absent():
    dms = [{"company_name": "Acme", "name": "Jane Doe"}]
    # Store key must be lowercase; a mismatched key yields a blank email.
    ws = _load([{"company_name": "Acme"}], dms, {("Acme", "Jane Doe"): "jane@acme.com"})["_dm_data"]
    assert ws.cell(row=2, column=5).value in (None, "")


# ── Grouped "Decision Makers" sheet ───────────────────────────────────────────

def test_decision_makers_grouped_sheet_layout():
    dms = [
        {
            "company_name": "Acme",
            "name": "Jane Doe",
            "position": "CEO",
            "linkedin_url": "https://li/jane",
            "location": "BLR",
        },
        {"company_name": "Acme", "name": "John Roe", "position": "CFO"},
    ]
    email_store = {("acme", "jane doe"): "jane@acme.com"}
    ws = _load([{"company_name": "Acme"}], dms, email_store)["Decision Makers"]

    # Banner row (merged across A:F)
    assert ws.cell(row=1, column=1).value == "  ▸ Acme  (2 contacts)"
    assert "A1:F1" in [str(rng) for rng in ws.merged_cells.ranges]

    # Sub-header row
    assert [ws.cell(row=2, column=c).value for c in range(1, 7)] == GROUP_HEADERS

    # First contact row
    assert ws.cell(row=3, column=1).value == 1
    assert ws.cell(row=3, column=2).value == "Jane Doe"
    assert ws.cell(row=3, column=3).value == "CEO"
    assert ws.cell(row=3, column=4).value == '=HYPERLINK("https://li/jane", "Jane Doe")'
    assert ws.cell(row=3, column=4).hyperlink is not None
    assert ws.cell(row=3, column=4).hyperlink.target == "https://li/jane"
    assert ws.cell(row=3, column=5).value == "jane@acme.com"
    assert ws.cell(row=3, column=6).value == "BLR"

    # Second contact row: no LinkedIn/email -> placeholders, location falls back to company
    assert ws.cell(row=4, column=2).value == "John Roe"
    assert ws.cell(row=4, column=4).value == "—"
    assert ws.cell(row=4, column=5).value == "—"
    assert ws.cell(row=4, column=6).value == "BLR"


def test_decision_makers_email_falls_back_to_dm_dict():
    dms = [{"company_name": "Acme", "name": "Jane", "email": "fallback@acme.com"}]
    ws = _load([{"company_name": "Acme"}], dms, {})["Decision Makers"]

    assert ws.cell(row=3, column=2).value == "Jane"
    assert ws.cell(row=3, column=5).value == "fallback@acme.com"


def test_contact_with_missing_fields_renders_placeholders():
    dms = [{"company_name": "Acme", "name": "Jane"}]
    ws = _load([{"company_name": "Acme"}], dms, {})["Decision Makers"]

    # A contact row with no LinkedIn, email or location still renders "—" placeholders.
    assert ws.cell(row=3, column=4).value == "—"
    assert ws.cell(row=3, column=5).value == "—"
    assert ws.cell(row=3, column=6).value == "—"


def test_company_without_dms_renders_no_banner():
    # NOTE: builder only iterates the DM list, so a company with zero DMs emits no
    # "Decision Makers" rows (unlike exporters/report.py which emits a "—" placeholder).
    ws = _load([{"company_name": "Acme"}], [])["Decision Makers"]
    assert ws.cell(row=1, column=1).value is None


def test_decision_makers_grouped_per_company_in_sorted_order():
    dms = [
        {"company_name": "Zeta", "name": "Z1"},
        {"company_name": "Acme", "name": "A1"},
    ]
    ws = _load([{"company_name": "Zeta"}, {"company_name": "Acme"}], dms, {})["Decision Makers"]

    assert ws.cell(row=1, column=1).value == "  ▸ Acme  (1 contacts)"
    # Acme: banner(1) + subheader(2) + contact(3) + spacer(4) -> Zeta banner at row 5
    assert ws.cell(row=5, column=1).value == "  ▸ Zeta  (1 contacts)"
