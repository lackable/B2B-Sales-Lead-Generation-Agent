"""Unit tests for the LinkedIn Finder pydantic schemas (pure, hermetic)."""

import pytest
from pydantic import ValidationError

from leadgen.agents.linkedin_finder.schemas import (
    DecisionMaker,
    DecisionMakerList,
    GeneratedQuery,
    ResearchLoopDecision,
)

VALID_DM = {
    "name": "Jane Doe",
    "position": "Chief Executive Officer",
    "linkedin_url": "https://www.linkedin.com/in/janedoe",
}


class TestDecisionMaker:
    def test_round_trips_all_fields(self):
        dm = DecisionMaker(**VALID_DM)

        assert dm.name == "Jane Doe"
        assert dm.position == "Chief Executive Officer"
        assert dm.linkedin_url == "https://www.linkedin.com/in/janedoe"
        assert dm.model_dump() == VALID_DM

    @pytest.mark.parametrize("missing_field", ["name", "position", "linkedin_url"])
    def test_every_field_is_required(self, missing_field):
        payload = dict(VALID_DM)
        payload.pop(missing_field)

        with pytest.raises(ValidationError) as exc_info:
            DecisionMaker(**payload)

        assert missing_field in str(exc_info.value)


class TestDecisionMakerList:
    def test_defaults_to_empty_list(self):
        assert DecisionMakerList().decision_makers == []

    def test_default_list_is_not_shared_between_instances(self):
        first = DecisionMakerList()
        second = DecisionMakerList()

        first.decision_makers.append(DecisionMaker(**VALID_DM))

        assert len(first.decision_makers) == 1
        assert second.decision_makers == []

    def test_accepts_list_of_dicts(self):
        parsed = DecisionMakerList(decision_makers=[VALID_DM, {**VALID_DM, "name": "John Roe"}])

        assert [dm.name for dm in parsed.decision_makers] == ["Jane Doe", "John Roe"]
        assert isinstance(parsed.decision_makers[0], DecisionMaker)

    def test_rejects_invalid_nested_entry(self):
        with pytest.raises(ValidationError):
            DecisionMakerList(decision_makers=[{"name": "Jane Doe"}])


class TestResearchLoopDecision:
    @pytest.mark.parametrize("status", ["NEEDED", "NOT_NEEDED"])
    def test_accepts_only_the_two_literals(self, status):
        decision = ResearchLoopDecision(status=status, reasoning="Because reasons.")

        assert decision.status == status
        assert decision.reasoning == "Because reasons."

    @pytest.mark.parametrize("status", ["MAYBE", "needed", "not_needed", "", "DONE"])
    def test_invalid_literal_raises_validation_error(self, status):
        with pytest.raises(ValidationError) as exc_info:
            ResearchLoopDecision(status=status, reasoning="nope")

        message = str(exc_info.value)
        assert "NEEDED" in message
        assert "NOT_NEEDED" in message

    def test_reasoning_is_required(self):
        with pytest.raises(ValidationError) as exc_info:
            ResearchLoopDecision(status="NEEDED")

        assert "reasoning" in str(exc_info.value)


class TestGeneratedQuery:
    def test_stores_query(self):
        assert GeneratedQuery(query="site:linkedin.com/in Acme CEO").query == "site:linkedin.com/in Acme CEO"

    def test_query_is_required(self):
        with pytest.raises(ValidationError) as exc_info:
            GeneratedQuery()

        assert "query" in str(exc_info.value)
