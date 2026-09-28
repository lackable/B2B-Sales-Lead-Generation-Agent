"""Hermetic unit tests for the Shortlister -> LinkedIn Finder subgraph bridge."""

import pytest

from leadgen.agents.shortlister.subgraphs import linkedin_finder as lf
from leadgen.agents.shortlister.subgraphs.linkedin_finder import (
    _get_contact_finder,
    _run_linkedin_finder_subgraph_impl,
    run_linkedin_finder_subgraph,
)
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


# ── _get_contact_finder ───────────────────────────────────────────────────────


def test_get_contact_finder_compiles_once_and_caches(monkeypatch):
    monkeypatch.setattr(lf, "_cached_contact_finder", None)
    compiled = object()
    calls = {"count": 0}

    class _FakeBuilder:
        def compile(self):
            calls["count"] += 1
            return compiled

    monkeypatch.setattr(lf, "contact_finder_builder", _FakeBuilder())

    first = _get_contact_finder()
    second = _get_contact_finder()

    assert first is compiled
    assert second is compiled
    assert calls["count"] == 1
    assert lf._cached_contact_finder is compiled


# ── _run_linkedin_finder_subgraph_impl ────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_impl_returns_decision_makers_and_passes_state(monkeypatch):
    captured = {}

    class _FakeGraph:
        async def ainvoke(self, initial_state, config=None):
            captured["state"] = initial_state
            captured["config"] = config
            return {"decision_makers": [{"name": "Jane", "position": "CEO"}]}

    monkeypatch.setattr(lf, "_get_contact_finder", lambda: _FakeGraph())

    decision_makers = await _run_linkedin_finder_subgraph_impl(
        company_name="Acme Corp",
        company_website="https://acme.com",
        company_linkedin="",
        location="Mumbai",
        session_id="sess-1",
    )

    assert decision_makers == [{"name": "Jane", "position": "CEO"}]
    assert captured["state"] == {
        "company_name": "Acme Corp",
        "company_linkedin": "",
        "company_website": "https://acme.com",
        "location": "Mumbai",
        "generated_query": "",
        "serp_raw_response": {},
        "ai_overview": "",
        "decision_makers": [],
        "scrape_calls_used": 0,
        "loop_memory": [],
        "session_id": "sess-1",
    }
    assert captured["config"] == {"configurable": {"thread_id": "sess-1"}}


@pytest.mark.asyncio
async def test_run_impl_applies_defaults_for_missing_fields(monkeypatch):
    captured = {}

    class _FakeGraph:
        async def ainvoke(self, initial_state, config=None):
            captured["state"] = initial_state
            return {"decision_makers": []}

    monkeypatch.setattr(lf, "_get_contact_finder", lambda: _FakeGraph())

    decision_makers = await _run_linkedin_finder_subgraph_impl("Acme", None, None, None, "sess-2")

    assert decision_makers == []
    assert captured["state"]["company_linkedin"] == ""
    assert captured["state"]["company_website"] == ""
    assert captured["state"]["location"] == "India"


@pytest.mark.asyncio
async def test_run_impl_returns_empty_list_when_graph_raises(monkeypatch, capsys):
    class _BoomGraph:
        async def ainvoke(self, initial_state, config=None):
            raise RuntimeError("graph failed")

    monkeypatch.setattr(lf, "_get_contact_finder", lambda: _BoomGraph())

    decision_makers = await _run_linkedin_finder_subgraph_impl("Acme", "https://acme.com", "", "India", "sess-3")

    assert decision_makers == []
    out = capsys.readouterr().out
    assert "[LinkedIn Finder Subgraph Error]" in out
    assert "RuntimeError: graph failed" in out


# ── run_linkedin_finder_subgraph ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_linkedin_finder_subgraph_emits_lifecycle(monkeypatch, capture_events):
    async def fake_impl(company_name, company_website, company_linkedin, location, session_id):
        return [{"name": "Jane", "position": "CEO"}]

    monkeypatch.setattr(lf, "_run_linkedin_finder_subgraph_impl", fake_impl)

    decision_makers = await run_linkedin_finder_subgraph(
        company_name="Acme Corp",
        company_website="https://acme.com",
        company_linkedin="",
        location="India",
        session_id="sess-9",
        parent_session_id="parent-1",
    )

    assert decision_makers == [{"name": "Jane", "position": "CEO"}]

    starts = capture_events.of("subagent_start")
    ends = capture_events.of("subagent_end")
    assert len(starts) == 1
    assert len(ends) == 1
    assert starts[0]["data"]["branch"] == "linkedin_contact_finder"
    assert starts[0]["data"]["execution_id"] == "sess-9:contact-finder"
    assert starts[0]["data"]["parent_execution_id"] == "sess-9"
    assert ends[0]["data"]["branch"] == "linkedin_contact_finder"
    assert ends[0]["data"]["contact_count"] == 1
    assert ends[0]["data"]["status"] == "completed"


@pytest.mark.asyncio
async def test_run_linkedin_finder_subgraph_uses_session_when_parent_missing(monkeypatch, capture_events):
    async def fake_impl(company_name, company_website, company_linkedin, location, session_id):
        return []

    monkeypatch.setattr(lf, "_run_linkedin_finder_subgraph_impl", fake_impl)

    decision_makers = await run_linkedin_finder_subgraph(
        company_name="Acme",
        company_website="https://acme.com",
        company_linkedin="",
        location="India",
        session_id="sess-10",
    )

    assert decision_makers == []
    ends = capture_events.of("subagent_end")
    assert ends[0]["data"]["contact_count"] == 0
    assert ends[0]["data"]["company"] == "Acme"
    assert ends[0]["data"]["execution_id"] == "sess-10:contact-finder"
