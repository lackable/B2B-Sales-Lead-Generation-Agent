"""Hermetic unit tests for the Shortlister agent state models and reducers."""

from leadgen.agents.shortlister.state import (
    ConductResearch,
    ResearchComplete,
    ResearcherOutputState,
    ScreenerQuery,
    override_reducer,
)

# ── ScreenerQuery ─────────────────────────────────────────────────────────────


def test_screener_query_defaults():
    query = ScreenerQuery(sector="Technology Services")

    assert query.sector == "Technology Services"
    assert query.industry is None
    assert query.revenue_min is None
    assert query.revenue_max is None
    assert query.profit_min is None
    assert query.profit_max is None
    assert query.market == "india"
    assert query.location == "India"
    assert query.limit == 60


def test_screener_query_field_serialization():
    query = ScreenerQuery(
        sector="Finance",
        industry="Major Banks",
        revenue_min=5_000_000_000,
        revenue_max=50_000_000_000,
        profit_min=100,
        profit_max=200,
        market="india",
        location="India",
        limit=25,
    )

    assert query.model_dump() == {
        "sector": "Finance",
        "industry": "Major Banks",
        "revenue_min": 5_000_000_000,
        "revenue_max": 50_000_000_000,
        "profit_min": 100,
        "profit_max": 200,
        "market": "india",
        "location": "India",
        "limit": 25,
    }


def test_screener_query_partial_serialization_keeps_optional_none():
    query = ScreenerQuery(sector="Retail Trade", limit=5)

    dumped = query.model_dump()
    assert dumped["sector"] == "Retail Trade"
    assert dumped["industry"] is None
    assert dumped["market"] == "india"
    assert dumped["limit"] == 5


# ── override_reducer ──────────────────────────────────────────────────────────


def test_override_reducer_override_dict_returns_value():
    assert override_reducer(["old"], {"type": "override", "value": ["new"]}) == ["new"]
    assert override_reducer("old", {"type": "override", "value": "scalar"}) == "scalar"


def test_override_reducer_override_dict_without_value_returns_dict():
    marker = {"type": "override"}

    assert override_reducer(["old"], marker) == {"type": "override"}


def test_override_reducer_list_plus_list_concatenates():
    assert override_reducer([1, 2], [3, 4]) == [1, 2, 3, 4]


def test_override_reducer_list_plus_scalar_appends():
    assert override_reducer(["a"], "b") == ["a", "b"]
    assert override_reducer([{"x": 1}], {"y": 2}) == [{"x": 1}, {"y": 2}]


def test_override_reducer_scalar_replaces():
    assert override_reducer("old", "new") == "new"
    assert override_reducer(None, 42) == 42


# ── ResearcherOutputState ─────────────────────────────────────────────────────


def test_researcher_output_state_raw_notes_default_factory_is_fresh_list():
    first = ResearcherOutputState(compressed_research="one")
    second = ResearcherOutputState(compressed_research="two")

    assert first.raw_notes == []
    assert second.raw_notes == []
    assert first.raw_notes is not second.raw_notes


# ── ConductResearch / ResearchComplete ────────────────────────────────────────


def test_conduct_research_model_fields():
    call = ConductResearch(
        company_name="Acme",
        website="https://acme.com",
        research_topic="find the official LinkedIn page",
    )

    assert call.company_name == "Acme"
    assert call.website == "https://acme.com"
    assert call.research_topic == "find the official LinkedIn page"
    assert call.description is None


def test_research_complete_model_has_no_fields():
    assert ResearchComplete().model_dump() == {}
