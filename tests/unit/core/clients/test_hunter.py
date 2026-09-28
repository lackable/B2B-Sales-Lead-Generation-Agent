"""Unit tests for :mod:`leadgen.core.clients.hunter`."""

import pytest

from leadgen.core.clients import hunter


class _FakeResponse:
    def __init__(self, payload=None, raise_json=False, status_code=200, text="raw body"):
        self._payload = payload
        self._raise_json = raise_json
        self.status_code = status_code
        self.text = text
        self.raise_for_status_calls = 0

    def json(self):
        if self._raise_json:
            raise ValueError("not json")
        return self._payload

    def raise_for_status(self):
        self.raise_for_status_calls += 1


def _install_get(monkeypatch, response, recorded):
    def fake_get(url, params=None, timeout=None):
        recorded["url"] = url
        recorded["params"] = params
        recorded["timeout"] = timeout
        return response

    monkeypatch.setattr(hunter.requests, "get", fake_get)


# ── get_hunter_api_key ────────────────────────────────────────────────────────

def test_get_hunter_api_key_explicit_argument_wins(monkeypatch):
    monkeypatch.setattr(hunter.config, "HUNTER_API_KEY", "config-key")
    assert hunter.get_hunter_api_key("explicit-key") == "explicit-key"


def test_get_hunter_api_key_falls_back_to_config(monkeypatch):
    monkeypatch.setattr(hunter.config, "HUNTER_API_KEY", "config-key")
    assert hunter.get_hunter_api_key() == "config-key"
    assert hunter.get_hunter_api_key(None) == "config-key"


# ── extract_linkedin_handle ───────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://www.linkedin.com/in/alexisohanian/", "alexisohanian"),
        ("http://linkedin.com/in/john-doe-12345", "john-doe-12345"),
        ("https://linkedin.com/in/jane/", "jane"),
        ("plainhandle", "plainhandle"),
        ("@handle", "handle"),
        ("https://www.LINKEDIN.com/in/MixedCase99/", "MixedCase99"),
        ("handle/", "handle"),
        ("  padded-handle  ", "padded-handle"),
    ],
)
def test_extract_linkedin_handle(raw, expected):
    assert hunter.extract_linkedin_handle(raw) == expected


# ── find_email_by_linkedin ────────────────────────────────────────────────────

def test_find_email_by_linkedin_missing_key_raises(monkeypatch):
    monkeypatch.setattr(hunter.config, "HUNTER_API_KEY", None)
    with pytest.raises(ValueError):
        hunter.find_email_by_linkedin("https://linkedin.com/in/someone")


def test_find_email_by_linkedin_required_params_only(monkeypatch):
    monkeypatch.setattr(hunter.config, "HUNTER_API_KEY", "config-key")
    response = _FakeResponse(payload={"data": {"email": "a@b.com"}})
    recorded = {}
    _install_get(monkeypatch, response, recorded)

    result = hunter.find_email_by_linkedin("https://linkedin.com/in/jane-doe")

    assert result == {"data": {"email": "a@b.com"}}
    assert recorded["url"] == hunter.HUNTER_EMAIL_FINDER_URL
    assert recorded["timeout"] == 30
    assert recorded["params"] == {
        "linkedin_handle": "jane-doe",
        "api_key": "config-key",
        "max_duration": 10,
    }


def test_find_email_by_linkedin_includes_supplied_optional_fields(monkeypatch):
    monkeypatch.setattr(hunter.config, "HUNTER_API_KEY", "config-key")
    response = _FakeResponse(payload={"data": {}})
    recorded = {}
    _install_get(monkeypatch, response, recorded)

    result = hunter.find_email_by_linkedin(
        "https://linkedin.com/in/jane",
        api_key="explicit-key",
        first_name="Jane",
        last_name="Doe",
        full_name="Jane Doe",
        domain="acme.com",
        company="Acme",
        max_duration=20,
    )

    assert result == {"data": {}}
    assert recorded["params"] == {
        "linkedin_handle": "jane",
        "api_key": "explicit-key",
        "max_duration": 20,
        "first_name": "Jane",
        "last_name": "Doe",
        "full_name": "Jane Doe",
        "domain": "acme.com",
        "company": "Acme",
    }


def test_find_email_by_linkedin_json_failure_returns_raw_fallback(monkeypatch):
    monkeypatch.setattr(hunter.config, "HUNTER_API_KEY", "config-key")
    response = _FakeResponse(raise_json=True, status_code=503, text="upstream unavailable")
    recorded = {}
    _install_get(monkeypatch, response, recorded)

    result = hunter.find_email_by_linkedin("handle-x")

    assert result == {"status_code": 503, "raw_response": "upstream unavailable"}
    assert response.raise_for_status_calls == 1
