"""Unit tests for the FastAPI request models in ``leadgen.api.schemas``."""

import pytest
from pydantic import ValidationError

from leadgen.api.schemas import (
    HunterEmailRequest,
    HunterSmartEnrichDM,
    HunterSmartEnrichRequest,
    LinkedInCompany,
    LinkedInRequest,
    ShortlisterRequest,
    StoreEmailRequest,
)

COMPANY = {"company_name": "Acme Corp", "linkedin_url": "https://linkedin.com/company/acme", "website": "https://acme.com"}


class TestShortlisterRequest:
    def test_query_is_required(self):
        with pytest.raises(ValidationError) as exc_info:
            ShortlisterRequest()

        assert "query" in str(exc_info.value)

    def test_stores_query(self):
        assert ShortlisterRequest(query="indian it companies").query == "indian it companies"

    def test_query_must_be_a_string(self):
        with pytest.raises(ValidationError):
            ShortlisterRequest(query=["not", "a", "string"])


class TestLinkedInCompany:
    def test_all_fields_are_required(self):
        for missing in ("company_name", "linkedin_url", "website"):
            payload = dict(COMPANY)
            payload.pop(missing)

            with pytest.raises(ValidationError) as exc_info:
                LinkedInCompany(**payload)

            assert missing in str(exc_info.value)

    def test_model_dump_keys_are_exact(self):
        company = LinkedInCompany(**COMPANY)

        assert company.model_dump() == COMPANY
        assert list(company.model_dump().keys()) == ["company_name", "linkedin_url", "website"]


class TestLinkedInRequest:
    def test_companies_is_required(self):
        with pytest.raises(ValidationError) as exc_info:
            LinkedInRequest()

        assert "companies" in str(exc_info.value)

    def test_concurrency_defaults_to_ten(self):
        request = LinkedInRequest(companies=[])

        assert request.concurrency == 10
        assert request.companies == []

    def test_concurrency_can_be_overridden(self):
        assert LinkedInRequest(companies=[], concurrency=3).concurrency == 3

    def test_companies_accepts_a_list_of_dicts(self):
        request = LinkedInRequest(companies=[COMPANY, {**COMPANY, "company_name": "Beta Ltd"}], concurrency=5)

        assert [c.company_name for c in request.companies] == ["Acme Corp", "Beta Ltd"]
        assert all(isinstance(c, LinkedInCompany) for c in request.companies)
        assert request.companies[1].website == "https://acme.com"
        assert request.concurrency == 5

    def test_invalid_company_payload_is_rejected(self):
        with pytest.raises(ValidationError):
            LinkedInRequest(companies=[{"company_name": "Acme Corp"}])


class TestHunterEmailRequest:
    def test_only_linkedin_url_is_required(self):
        request = HunterEmailRequest(linkedin_url="https://linkedin.com/in/janedoe")

        assert request.linkedin_url == "https://linkedin.com/in/janedoe"
        assert request.first_name is None
        assert request.last_name is None
        assert request.full_name is None
        assert request.domain is None
        assert request.company is None

    def test_linkedin_url_is_required(self):
        with pytest.raises(ValidationError) as exc_info:
            HunterEmailRequest()

        assert "linkedin_url" in str(exc_info.value)

    def test_optional_fields_round_trip(self):
        request = HunterEmailRequest(
            linkedin_url="jane-doe",
            first_name="Jane",
            last_name="Doe",
            full_name="Jane Doe",
            domain="acme.com",
            company="Acme Corp",
        )

        assert request.model_dump() == {
            "linkedin_url": "jane-doe",
            "first_name": "Jane",
            "last_name": "Doe",
            "full_name": "Jane Doe",
            "domain": "acme.com",
            "company": "Acme Corp",
        }


class TestStoreEmailRequest:
    def test_all_fields_are_required(self):
        for missing in ("company_name", "dm_name", "email"):
            payload = {"company_name": "Acme Corp", "dm_name": "Jane Doe", "email": "jane@acme.com"}
            payload.pop(missing)

            with pytest.raises(ValidationError) as exc_info:
                StoreEmailRequest(**payload)

            assert missing in str(exc_info.value)

    def test_stores_payload(self):
        request = StoreEmailRequest(company_name="Acme Corp", dm_name="Jane Doe", email="jane@acme.com")

        assert request.model_dump() == {
            "company_name": "Acme Corp",
            "dm_name": "Jane Doe",
            "email": "jane@acme.com",
        }


class TestHunterSmartEnrichDM:
    def test_only_id_is_required(self):
        dm = HunterSmartEnrichDM(id="dm-1")

        assert dm.id == "dm-1"
        assert dm.name is None
        assert dm.linkedin_url is None
        assert dm.company_name is None
        assert dm.company_website is None
        assert dm.position is None

    def test_id_is_required(self):
        with pytest.raises(ValidationError) as exc_info:
            HunterSmartEnrichDM()

        assert "id" in str(exc_info.value)

    def test_all_optional_fields_round_trip(self):
        dm = HunterSmartEnrichDM(
            id="dm-1",
            name="Jane Doe",
            linkedin_url="https://linkedin.com/in/janedoe",
            company_name="Acme Corp",
            company_website="https://acme.com",
            position="CEO",
        )

        assert dm.model_dump() == {
            "id": "dm-1",
            "name": "Jane Doe",
            "linkedin_url": "https://linkedin.com/in/janedoe",
            "company_name": "Acme Corp",
            "company_website": "https://acme.com",
            "position": "CEO",
        }


class TestHunterSmartEnrichRequest:
    def test_decision_makers_is_required(self):
        with pytest.raises(ValidationError) as exc_info:
            HunterSmartEnrichRequest()

        assert "decision_makers" in str(exc_info.value)

    def test_accepts_dicts_and_coerces_them(self):
        request = HunterSmartEnrichRequest(decision_makers=[{"id": "dm-1"}, {"id": "dm-2", "name": "Jane"}])

        assert [dm.id for dm in request.decision_makers] == ["dm-1", "dm-2"]
        assert all(isinstance(dm, HunterSmartEnrichDM) for dm in request.decision_makers)
        assert request.decision_makers[1].name == "Jane"

    def test_accepts_empty_list(self):
        assert HunterSmartEnrichRequest(decision_makers=[]).decision_makers == []

    def test_entry_without_id_is_rejected(self):
        with pytest.raises(ValidationError):
            HunterSmartEnrichRequest(decision_makers=[{"name": "Jane Doe"}])
