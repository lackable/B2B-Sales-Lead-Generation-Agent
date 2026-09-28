"""Hermetic unit tests for the Shortlister LangGraph pipeline (graph.py)."""

import asyncio
import os
import re

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END

from leadgen.agents.shortlister import graph, scraping
from leadgen.agents.shortlister.graph import (
    _emit,
    _search_company_linkedin_impl,
    build_graph,
    cleaner,
    enrich_single_company,
    excel_exporter_node,
    get_now_str,
    linkedin_verifier,
    query_formulator,
    search_company_linkedin,
    shortlister_agent,
    shortlister_builder,
    yfinance_enricher,
)
from leadgen.agents.shortlister.state import ScreenerQuery
from leadgen.core.telemetry.registry import get_logger, register_logger


class CapturingLogger:
    """Minimal structured logger that records every emitted event."""

    def __init__(self):
        self.events = []

    def event(self, event_type, data, *, level=None, component=None):
        self.events.append({"event_type": event_type, "data": dict(data), "level": level, "component": component})

    def of(self, event_type):
        return [event for event in self.events if event["event_type"] == event_type]


@pytest.fixture
def capture_events():
    capture = CapturingLogger()
    previous = get_logger()
    register_logger(capture)
    try:
        yield capture
    finally:
        register_logger(previous)


# ── get_now_str / _emit ───────────────────────────────────────────────────────


def test_get_now_str_matches_expected_format():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", get_now_str())


def test_emit_noops_when_no_logger_registered():
    previous = get_logger()
    register_logger(None)
    try:
        _emit("node_enter", {"node_name": "x"})  # must not raise
    finally:
        register_logger(previous)


def test_emit_swallows_logger_errors():
    class _BoomLogger:
        def event(self, *args, **kwargs):
            raise RuntimeError("logger exploded")

    previous = get_logger()
    register_logger(_BoomLogger())
    try:
        _emit("node_enter", {"node_name": "x"})  # must not raise
    finally:
        register_logger(previous)


# ── query_formulator ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_formulator_returns_command_and_emits_event(monkeypatch, capture_events):
    expected = ScreenerQuery(
        sector="Technology Services",
        industry="Packaged Software",
        market="india",
        location="India",
        revenue_min=1000,
        revenue_max=2000,
        limit=25,
    )

    async def fake_invoke(model_or_factory, input_data, *args, **kwargs):
        return expected

    monkeypatch.setattr(graph, "invoke_model_with_rate_limit_retry", fake_invoke)

    state = {"messages": [HumanMessage(content="Tech firms in India")]}

    cmd = await query_formulator(state, {"configurable": {}})

    assert cmd.goto == "screener_fetch"
    assert cmd.update["screener_query"] is expected

    exits = [
        event
        for event in capture_events.of("node_exit")
        if event["data"]["node_name"] == "query_formulator"
    ]
    assert len(exits) == 1
    summary = exits[0]["data"]["output_summary"]
    assert summary["sector"] == "Technology Services"
    assert summary["industry"] == "Packaged Software"
    assert summary["market"] == "india"
    assert summary["location"] == "India"
    assert summary["revenue_min"] == 1000
    assert summary["revenue_max"] == 2000
    assert summary["limit"] == 25
    assert summary["slots"] == {
        "SECTOR": "Technology Services",
        "INDUSTRY": "Packaged Software",
        "MARKET": "india",
        "LOCATION": "India",
        "LIMIT": "25",
    }
    assert capture_events.of("node_enter")[0]["component"] == "agents.shortlister.graph"


@pytest.mark.asyncio
async def test_query_formulator_uses_default_input_when_no_messages(monkeypatch):
    captured = {}

    async def fake_invoke(model_or_factory, input_data, *args, **kwargs):
        captured["messages"] = input_data
        return ScreenerQuery(sector="Finance")

    monkeypatch.setattr(graph, "invoke_model_with_rate_limit_retry", fake_invoke)

    cmd = await query_formulator({}, {"configurable": {}})

    assert cmd.goto == "screener_fetch"
    assert "Technology companies in India" in captured["messages"][0].content


@pytest.mark.asyncio
async def test_query_formulator_slots_fallback_defaults(monkeypatch):
    async def fake_invoke(model_or_factory, input_data, *args, **kwargs):
        return ScreenerQuery(sector="", industry=None, market="", location="")

    monkeypatch.setattr(graph, "invoke_model_with_rate_limit_retry", fake_invoke)

    cmd = await query_formulator({"messages": [HumanMessage(content="anything")]}, {"configurable": {}})

    assert cmd.update["screener_query"].sector == ""


# ── enrich_single_company ─────────────────────────────────────────────────────


class _FakeYFinanceTicker:
    def __init__(self, info=None, error=None):
        self._info = info
        self._error = error

    @property
    def info(self):
        if self._error is not None:
            raise self._error
        return self._info


class _TickerFactory:
    """Records which Yahoo ticker symbols ``yf.Ticker`` was called with."""

    def __init__(self, info=None, error=None):
        self.created = []
        self._info = info
        self._error = error

    def __call__(self, symbol):
        self.created.append(symbol)
        return _FakeYFinanceTicker(self._info, self._error)


@pytest.mark.asyncio
async def test_enrich_single_company_full_info(monkeypatch):
    factory = _TickerFactory(
        info={
            "fullTimeEmployees": 5000,
            "longBusinessSummary": "IT services worldwide.",
            "website": "https://www.tcs.com",
            "longName": "Tata Consultancy Services",
            "city": "Mumbai",
            "state": "Maharashtra",
            "country": "India",
        }
    )
    monkeypatch.setattr(graph.yf, "Ticker", factory)

    company = {
        "ticker": "NSE:TCS",
        "name": "TCS",
        "industry": "IT",
        "total_revenue_ttm": 100,
        "net_income_ttm": 10,
    }

    record = await enrich_single_company(company, asyncio.Semaphore(1))

    assert factory.created == ["TCS.NS"]
    assert record["ticker"] == "NSE:TCS"
    assert record["name"] == "Tata Consultancy Services"
    assert record["industry"] == "IT"
    assert record["revenue_ttm"] == 100
    assert record["net_income_ttm"] == 10
    assert record["employee_count"] == 5000
    assert record["business_summary"] == "IT services worldwide."
    assert record["website"] == "https://www.tcs.com"
    assert record["city"] == "Mumbai"
    assert record["state"] == "Maharashtra"
    assert record["country"] == "India"
    assert record["location"] == "Mumbai, Maharashtra, India"
    assert record["enrichment_source"] == "yfinance"
    assert record["linkedin_guessed"] is None
    assert record["linkedin_verified"] is None
    assert record["linkedin_confirmed"] is False


@pytest.mark.asyncio
async def test_enrich_single_company_bse_ticker_conversion(monkeypatch):
    factory = _TickerFactory(info={"longName": "Acme", "website": "https://acme.com"})
    monkeypatch.setattr(graph.yf, "Ticker", factory)

    record = await enrich_single_company({"ticker": "BSE:ACME", "name": "Acme"}, asyncio.Semaphore(1))

    assert factory.created == ["ACME.BO"]
    assert record["ticker"] == "BSE:ACME"
    assert record["name"] == "Acme"


@pytest.mark.asyncio
async def test_enrich_single_company_uses_financedatabase_fallback(monkeypatch):
    factory = _TickerFactory(info={"longName": "Acme", "website": "NONE"})
    monkeypatch.setattr(graph.yf, "Ticker", factory)

    calls = []

    def fake_fallback(ticker_str):
        calls.append(ticker_str)
        return "https://fallback.example.com"

    monkeypatch.setattr(graph, "fallback_financedatabase_website", fake_fallback)

    record = await enrich_single_company({"ticker": "NSE:ACME", "name": "Acme"}, asyncio.Semaphore(1))

    assert calls == ["NSE:ACME"]
    assert record["website"] == "https://fallback.example.com"
    assert record["enrichment_source"] == "financedatabase fallback"


@pytest.mark.asyncio
async def test_enrich_single_company_not_found_when_no_website_anywhere(monkeypatch):
    factory = _TickerFactory(info={"longName": "Acme"})
    monkeypatch.setattr(graph.yf, "Ticker", factory)
    monkeypatch.setattr(graph, "fallback_financedatabase_website", lambda ticker_str: None)

    record = await enrich_single_company({"ticker": "NSE:ACME", "name": "Acme"}, asyncio.Semaphore(1))

    assert record["website"] == "NOT FOUND"
    assert record["enrichment_source"] == "yfinance"


@pytest.mark.asyncio
async def test_enrich_single_company_survives_yfinance_error(monkeypatch):
    factory = _TickerFactory(error=RuntimeError("yfinance exploded"))
    monkeypatch.setattr(graph.yf, "Ticker", factory)
    monkeypatch.setattr(graph, "fallback_financedatabase_website", lambda ticker_str: None)

    record = await enrich_single_company({"ticker": "NSE:ACME", "name": "Acme Corp"}, asyncio.Semaphore(1))

    assert factory.created == ["ACME.NS"]
    assert record["website"] == "NOT FOUND"
    assert record["name"] == "Acme Corp"
    assert record["employee_count"] is None
    assert record["business_summary"] is None


@pytest.mark.asyncio
async def test_enrich_single_company_without_ticker(monkeypatch):
    factory = _TickerFactory(info={})
    monkeypatch.setattr(graph.yf, "Ticker", factory)

    record = await enrich_single_company({"name": "NoTicker"}, asyncio.Semaphore(1))

    assert factory.created == []
    assert record["ticker"] == ""
    assert record["website"] == "NOT FOUND"
    assert record["name"] == "NoTicker"


@pytest.mark.asyncio
async def test_enrich_single_company_uses_sector_when_industry_missing(monkeypatch):
    factory = _TickerFactory(info={"longName": "Acme", "website": "https://acme.com"})
    monkeypatch.setattr(graph.yf, "Ticker", factory)

    record = await enrich_single_company({"ticker": "NSE:ACME", "sector": "Finance"}, asyncio.Semaphore(1))

    assert record["industry"] == "Finance"


# ── yfinance_enricher ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_yfinance_enricher_gathers_enriched_and_gotos_cleaner(monkeypatch, capture_events):
    async def fake_enrich(company, sem):
        website = company.get("website", "https://ok.com")
        return {"name": company["name"], "website": website}

    monkeypatch.setattr(graph, "enrich_single_company", fake_enrich)

    state = {"raw_companies": [{"name": "A"}, {"name": "B"}]}

    cmd = await yfinance_enricher(state, {"configurable": {}})

    assert cmd.goto == "cleaner"
    assert [c["name"] for c in cmd.update["enriched_companies"]] == ["A", "B"]

    exits = [e for e in capture_events.of("node_exit") if e["data"]["node_name"] == "yfinance_enricher"]
    assert exits[0]["data"]["output_summary"] == {
        "total_enriched": 2,
        "websites_found": 2,
        "websites_missing": 0,
    }


@pytest.mark.asyncio
async def test_yfinance_enricher_counts_missing_websites(monkeypatch, capture_events):
    async def fake_enrich(company, sem):
        return {"name": company["name"], "website": company["website"]}

    monkeypatch.setattr(graph, "enrich_single_company", fake_enrich)

    state = {
        "raw_companies": [
            {"name": "A", "website": "https://a.com"},
            {"name": "B", "website": "NOT FOUND"},
        ]
    }

    cmd = await yfinance_enricher(state, {"configurable": {}})

    assert len(cmd.update["enriched_companies"]) == 2
    exits = [e for e in capture_events.of("node_exit") if e["data"]["node_name"] == "yfinance_enricher"]
    assert exits[0]["data"]["output_summary"]["websites_missing"] == 1


# ── cleaner ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cleaner_removes_not_found_and_sorts():
    sample_enriched = [
        {"name": "Comp A", "revenue_ttm": 100, "website": "https://compa.com"},
        {"name": "Comp B", "revenue_ttm": 500, "website": "NOT FOUND"},
        {"name": "Comp C", "revenue_ttm": 300, "website": "https://compc.com"},
        {"name": "Comp D", "revenue_ttm": 400, "website": "https://compd.com"},
    ]
    state = {"enriched_companies": sample_enriched}
    config = {"configurable": {"top_n_companies": 2}}

    cmd = await cleaner(state, config)
    cleaned = cmd.update.get("cleaned_companies", [])

    assert len(cleaned) == 2
    assert cleaned[0]["name"] == "Comp D"  # 400 revenue
    assert cleaned[1]["name"] == "Comp C"  # 300 revenue


@pytest.mark.asyncio
async def test_cleaner_drops_invalid_websites_and_emits_dropped(capture_events):
    enriched = [
        {"name": "Keep", "revenue_ttm": 50, "website": "https://keep.com"},
        {"name": "NotFound", "revenue_ttm": 100, "website": "NOT FOUND"},
        {"name": "LowerNone", "revenue_ttm": 200, "website": "none"},
        {"name": "LowerNan", "revenue_ttm": 300, "website": "nan"},
        {"name": "NoneWeb", "revenue_ttm": 400, "website": None},
        {"name": "EmptyWeb", "revenue_ttm": 500, "website": ""},
    ]

    cmd = await cleaner({"enriched_companies": enriched}, {"configurable": {"top_n_companies": 10}})

    assert [c["name"] for c in cmd.update["cleaned_companies"]] == ["Keep"]

    dropped = [event["data"] for event in capture_events.of("company_dropped")]
    assert dropped == [
        {"company_name": "NotFound", "reason": "missing website"},
        {"company_name": "LowerNone", "reason": "missing website"},
        {"company_name": "LowerNan", "reason": "missing website"},
    ]

    exits = [e for e in capture_events.of("node_exit") if e["data"]["node_name"] == "cleaner"]
    summary = exits[0]["data"]["output_summary"]
    assert summary["initial_count"] == 6
    assert summary["removed_count"] == 5
    assert summary["shortlisted_count"] == 1
    assert summary["top_companies"] == [{"name": "Keep", "revenue_ttm": 50}]

    assert cmd.goto == "linkedin_verifier"


@pytest.mark.asyncio
async def test_cleaner_sorts_none_revenue_last(capture_events):
    enriched = [
        {"name": "NoRev", "revenue_ttm": None, "website": "https://norev.com"},
        {"name": "HighRev", "revenue_ttm": 900, "website": "https://high.com"},
    ]

    cmd = await cleaner({"enriched_companies": enriched}, {"configurable": {"top_n_companies": 10}})

    assert [c["name"] for c in cmd.update["cleaned_companies"]] == ["HighRev", "NoRev"]
    exits = [e for e in capture_events.of("node_exit") if e["data"]["node_name"] == "cleaner"]
    assert exits[0]["data"]["output_summary"]["top_companies"] == [
        {"name": "HighRev", "revenue_ttm": 900},
        {"name": "NoRev", "revenue_ttm": None},
    ]


# ── _search_company_linkedin_impl ─────────────────────────────────────────────


def _base_comp():
    return {
        "name": "Acme Corp",
        "website": "https://acme.com",
        "business_summary": "We do things.",
        "revenue_ttm": 100,
    }


@pytest.mark.asyncio
async def test_search_impl_selenium_hit_skips_researcher(monkeypatch):
    monkeypatch.setattr(
        scraping,
        "extract_linkedin_from_website_selenium",
        lambda website_url, company_name="", timeout=12: "https://www.linkedin.com/company/acme",
    )

    researcher_calls = []

    class _FakeResearcher:
        async def ainvoke(self, state, config):
            researcher_calls.append(state)
            return {"compressed_research": "", "raw_notes": []}

    monkeypatch.setattr(graph, "researcher_subgraph", _FakeResearcher())

    finder_calls = []

    async def fake_finder(**kwargs):
        finder_calls.append(kwargs)
        return [{"name": "Jane", "position": "CEO", "linkedin_url": "https://linkedin.com/in/jane", "email": "j@acme.com"}]

    monkeypatch.setattr(graph, "run_linkedin_finder_subgraph", fake_finder)

    comp = _base_comp()
    result = await _search_company_linkedin_impl(
        comp, {"configurable": {"thread_id": "t1"}}, asyncio.Semaphore(1), "India"
    )

    assert result["linkedin_verified"] == "https://www.linkedin.com/company/acme"
    assert result["linkedin_confirmed"] is True
    assert researcher_calls == []
    assert result["decision_makers"] == [
        {"name": "Jane", "position": "CEO", "linkedin_url": "https://linkedin.com/in/jane", "email": "j@acme.com"}
    ]
    assert result["location"] == "India"
    assert finder_calls[0]["company_name"] == "Acme Corp"
    assert finder_calls[0]["session_id"] == "t1-AcmeCorp"
    assert finder_calls[0]["parent_session_id"] == "t1"


@pytest.mark.asyncio
async def test_search_impl_researcher_fallback_extracts_url_and_confirmation(monkeypatch):
    monkeypatch.setattr(scraping, "extract_linkedin_from_website_selenium", lambda *args, **kwargs: None)

    class _FakeResearcher:
        async def ainvoke(self, state, config):
            return {
                "compressed_research": (
                    "Verified LinkedIn URL: https://www.linkedin.com/company/acme\nLinkedIn Confirmed: Yes"
                ),
                "raw_notes": [],
            }

    monkeypatch.setattr(graph, "researcher_subgraph", _FakeResearcher())

    async def fake_finder(**kwargs):
        return []

    monkeypatch.setattr(graph, "run_linkedin_finder_subgraph", fake_finder)

    result = await _search_company_linkedin_impl(
        _base_comp(), {"configurable": {"thread_id": "t2"}}, asyncio.Semaphore(1), "India"
    )

    assert result["linkedin_verified"] == "https://www.linkedin.com/company/acme"
    assert result["linkedin_confirmed"] is True
    assert result["decision_makers"] == []
    assert result["location"] == "India"


@pytest.mark.asyncio
async def test_search_impl_researcher_reads_url_from_raw_notes(monkeypatch):
    monkeypatch.setattr(scraping, "extract_linkedin_from_website_selenium", lambda *args, **kwargs: None)

    class _FakeResearcher:
        async def ainvoke(self, state, config):
            return {
                "compressed_research": "",
                "raw_notes": ["snippet: see https://www.linkedin.com/company/beta-inc for details"],
            }

    monkeypatch.setattr(graph, "researcher_subgraph", _FakeResearcher())

    async def fake_finder(**kwargs):
        return []

    monkeypatch.setattr(graph, "run_linkedin_finder_subgraph", fake_finder)

    result = await _search_company_linkedin_impl(
        _base_comp(), {"configurable": {"thread_id": "t2b"}}, asyncio.Semaphore(1), "India"
    )

    assert result["linkedin_verified"] == "https://www.linkedin.com/company/beta-inc"
    assert result["linkedin_confirmed"] is True


@pytest.mark.asyncio
async def test_search_impl_researcher_error_sets_not_found(monkeypatch):
    monkeypatch.setattr(scraping, "extract_linkedin_from_website_selenium", lambda *args, **kwargs: None)

    class _BoomResearcher:
        async def ainvoke(self, state, config):
            raise RuntimeError("researcher exploded")

    monkeypatch.setattr(graph, "researcher_subgraph", _BoomResearcher())

    async def fake_finder(**kwargs):
        return []

    monkeypatch.setattr(graph, "run_linkedin_finder_subgraph", fake_finder)

    result = await _search_company_linkedin_impl(
        _base_comp(), {"configurable": {"thread_id": "t3"}}, asyncio.Semaphore(1), "India"
    )

    assert result["linkedin_verified"] == "NOT FOUND"
    assert result["linkedin_confirmed"] is False


@pytest.mark.asyncio
async def test_search_impl_preserves_existing_location(monkeypatch):
    monkeypatch.setattr(scraping, "extract_linkedin_from_website_selenium", lambda *args, **kwargs: None)
    monkeypatch.setattr(graph, "researcher_subgraph", _FakeResearcherSubgraph())

    async def fake_finder(**kwargs):
        return [{"name": "Bob", "position": "CTO"}]

    monkeypatch.setattr(graph, "run_linkedin_finder_subgraph", fake_finder)

    comp = _base_comp()
    comp["location"] = "Mumbai, Maharashtra, India"

    result = await _search_company_linkedin_impl(
        comp, {"configurable": {"thread_id": "t4"}}, asyncio.Semaphore(1), "India"
    )

    assert result["location"] == "Mumbai, Maharashtra, India"
    assert result["decision_makers"] == [{"name": "Bob", "position": "CTO"}]


class _FakeResearcherSubgraph:
    async def ainvoke(self, state, config):
        return {"compressed_research": "", "raw_notes": []}


# ── search_company_linkedin ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_company_linkedin_emits_contacts_snapshot(monkeypatch, capture_events):
    async def fake_impl(comp, config, sem, target_location):
        return {
            "name": comp["name"],
            "decision_makers": [
                {
                    "name": "Jane",
                    "position": "CEO",
                    "linkedin_url": "https://linkedin.com/in/jane",
                    "email": "j@acme.com",
                }
            ],
        }

    monkeypatch.setattr(graph, "_search_company_linkedin_impl", fake_impl)

    result = await search_company_linkedin(
        {"name": "Acme Corp"}, {"configurable": {"thread_id": "run-1"}}, asyncio.Semaphore(1), "India"
    )

    assert result["name"] == "Acme Corp"

    snapshots = capture_events.of("company_contacts_snapshot")
    assert len(snapshots) == 1
    data = snapshots[0]["data"]
    assert data["company"] == "Acme Corp"
    assert data["execution_id"] == "run-1-AcmeCorp"
    assert data["contact_count"] == 1
    assert data["contacts"] == [{"name": "Jane", "role": "CEO"}]
    assert snapshots[0]["component"] == "graph.shortlister"

    starts = [e for e in capture_events.of("subagent_start") if e["data"]["branch"] == "company_research"]
    ends = [e for e in capture_events.of("subagent_end") if e["data"]["branch"] == "company_research"]
    assert len(starts) == 1
    assert len(ends) == 1
    assert ends[0]["data"]["contact_count"] == 1
    assert ends[0]["data"]["status"] == "completed"


@pytest.mark.asyncio
async def test_search_company_linkedin_handles_no_decision_makers(monkeypatch, capture_events):
    async def fake_impl(comp, config, sem, target_location):
        return {"name": comp["name"], "decision_makers": []}

    monkeypatch.setattr(graph, "_search_company_linkedin_impl", fake_impl)

    await search_company_linkedin({"name": "Acme"}, {"configurable": {}}, asyncio.Semaphore(1), "India")

    data = capture_events.of("company_contacts_snapshot")[0]["data"]
    assert data["contact_count"] == 0
    assert data["contacts"] == []


# ── linkedin_verifier ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_linkedin_verifier_returns_verified_companies(monkeypatch, capture_events):
    seen_locations = []

    async def fake_search(comp, config, sem, target_location):
        seen_locations.append(target_location)
        return {
            **comp,
            "linkedin_verified": "https://www.linkedin.com/company/acme",
            "linkedin_confirmed": True,
            "decision_makers": [{"name": "Jane"}],
        }

    monkeypatch.setattr(graph, "search_company_linkedin", fake_search)

    state = {
        "cleaned_companies": [{"name": "Acme Corp"}],
        "screener_query": ScreenerQuery(sector="Technology Services", location="USA"),
    }

    cmd = await linkedin_verifier(state, {"configurable": {}})

    assert cmd.goto == "excel_exporter_node"
    verified = cmd.update["verified_companies"]
    assert len(verified) == 1
    assert verified[0]["linkedin_confirmed"] is True
    assert seen_locations == ["USA"]

    exits = [e for e in capture_events.of("node_exit") if e["data"]["node_name"] == "linkedin_verifier"]
    assert exits[0]["data"]["output_summary"] == {
        "companies_processed": 1,
        "linkedin_confirmed": 1,
        "total_contacts_found": 1,
    }

    progress = [
        e
        for e in capture_events.of("progress")
        if e["data"].get("stage") == "linkedin_verifier" and e["data"].get("progress_pct") == 90
    ]
    assert len(progress) == 1
    assert progress[0]["data"]["count"] == 1


@pytest.mark.asyncio
async def test_linkedin_verifier_defaults_location_to_india(monkeypatch):
    seen_locations = []

    async def fake_search(comp, config, sem, target_location):
        seen_locations.append(target_location)
        return {**comp, "linkedin_confirmed": False, "decision_makers": []}

    monkeypatch.setattr(graph, "search_company_linkedin", fake_search)

    cmd = await linkedin_verifier({"cleaned_companies": [{"name": "Acme"}]}, {"configurable": {}})

    assert cmd.goto == "excel_exporter_node"
    assert seen_locations == ["India"]


# ── excel_exporter_node ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_excel_exporter_node_returns_end_with_report_filename(monkeypatch, capture_events):
    saved = {}
    excel_path = os.path.join("runs", "shortlister", "report_x.xlsx")

    def fake_save_all(verified_companies, screener_query=None, session_id="session"):
        saved["companies"] = verified_companies
        saved["screener_query"] = screener_query
        saved["session_id"] = session_id
        return {"excel": excel_path, "json": os.path.join("runs", "shortlister", "report_x.json")}

    monkeypatch.setattr(graph, "save_all", fake_save_all)

    state = {
        "verified_companies": [{"name": "Acme", "decision_makers": [{"name": "J"}, {"name": "K"}]}],
        "screener_query": ScreenerQuery(sector="Finance"),
    }

    cmd = await excel_exporter_node(state, {"configurable": {"thread_id": "sess-1"}})

    assert cmd.goto == END
    assert saved["session_id"] == "sess-1"
    assert saved["screener_query"]["sector"] == "Finance"
    assert saved["companies"] == state["verified_companies"]

    exits = [e for e in capture_events.of("node_exit") if e["data"]["node_name"] == "excel_exporter_node"]
    summary = exits[0]["data"]["output_summary"]
    assert summary["report_filename"] == "report_x.xlsx"
    assert summary["excel_path"] == excel_path
    assert summary["company_count"] == 1
    assert summary["contact_count"] == 2


@pytest.mark.asyncio
async def test_excel_exporter_node_without_screener_query(monkeypatch, capture_events):
    saved = {}

    def fake_save_all(verified_companies, screener_query=None, session_id="session"):
        saved["screener_query"] = screener_query
        return {"excel": "", "json": ""}

    monkeypatch.setattr(graph, "save_all", fake_save_all)

    cmd = await excel_exporter_node({"verified_companies": []}, {"configurable": {}})

    assert cmd.goto == END
    assert saved["screener_query"] == {}

    exits = [e for e in capture_events.of("node_exit") if e["data"]["node_name"] == "excel_exporter_node"]
    assert exits[0]["data"]["output_summary"]["report_filename"] == ""


# ── graph construction ────────────────────────────────────────────────────────


def test_build_graph_compiles_with_memory_checkpointer():
    compiled = build_graph(checkpointer=MemorySaver())

    assert compiled is not None
    assert hasattr(compiled, "ainvoke")
    node_names = set(compiled.get_graph().nodes.keys())
    assert {
        "query_formulator",
        "screener_fetch",
        "yfinance_enricher",
        "cleaner",
        "linkedin_verifier",
        "excel_exporter_node",
    } <= node_names


def test_shortlister_builder_and_agent_exist():
    assert shortlister_builder is not None
    assert shortlister_agent is not None
    assert "query_formulator" in shortlister_builder.nodes
    assert "excel_exporter_node" in shortlister_builder.nodes
