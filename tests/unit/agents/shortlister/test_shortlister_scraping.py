"""Hermetic unit tests for the Shortlister scraping helpers."""

import sys

from leadgen.agents.shortlister import scraping
from leadgen.agents.shortlister.scraping import (
    _clean_linkedin_url,
    _normalize_website_url,
    extract_linkedin_from_website_selenium,
)

# ── _normalize_website_url ────────────────────────────────────────────────────


def test_normalize_website_url_invalid_values_return_empty():
    assert _normalize_website_url("") == ""
    assert _normalize_website_url("not found") == ""
    assert _normalize_website_url("NONE") == ""
    assert _normalize_website_url("nan") == ""
    assert _normalize_website_url(None) == ""


def test_normalize_website_url_adds_scheme_when_missing():
    assert _normalize_website_url("acme.com") == "https://acme.com"
    assert _normalize_website_url("  acme.com  ") == "https://acme.com"


def test_normalize_website_url_preserves_existing_scheme():
    assert _normalize_website_url("http://acme.com") == "http://acme.com"
    assert _normalize_website_url("https://acme.com") == "https://acme.com"


# ── _clean_linkedin_url ───────────────────────────────────────────────────────


def test_clean_linkedin_url_empty_returns_empty():
    assert _clean_linkedin_url("") == ""


def test_clean_linkedin_url_rebuilds_on_www_host():
    assert (
        _clean_linkedin_url("https://in.linkedin.com/company/acme")
        == "https://www.linkedin.com/company/acme"
    )


def test_clean_linkedin_url_strips_trailing_punctuation():
    assert (
        _clean_linkedin_url("https://www.linkedin.com/company/acme.")
        == "https://www.linkedin.com/company/acme"
    )
    assert (
        _clean_linkedin_url('https://www.linkedin.com/company/acme",')
        == "https://www.linkedin.com/company/acme"
    )


def test_clean_linkedin_url_strips_trailing_slash():
    assert (
        _clean_linkedin_url("https://www.linkedin.com/company/acme/")
        == "https://www.linkedin.com/company/acme"
    )


# ── Selenium extraction with httpx fallback ───────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


class _FakeClient:
    """Minimal httpx.Client stand-in that records requested URLs."""

    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc
        self.requested = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url):
        self.requested.append(url)
        if self._exc is not None:
            raise self._exc
        return self._response


def _force_selenium_unavailable(monkeypatch):
    """Make ``from selenium import webdriver`` raise so the httpx fallback runs."""
    monkeypatch.setitem(sys.modules, "selenium", None)


def test_extract_returns_none_for_invalid_website():
    assert extract_linkedin_from_website_selenium("") is None
    assert extract_linkedin_from_website_selenium("not found") is None


def test_extract_falls_back_to_httpx_when_selenium_unavailable(monkeypatch):
    _force_selenium_unavailable(monkeypatch)
    html = '<a href="https://www.linkedin.com/company/acme/">Acme on LinkedIn</a>'
    fake = _FakeClient(response=_FakeResponse(200, html))
    monkeypatch.setattr(scraping.httpx, "Client", lambda *args, **kwargs: fake)

    result = extract_linkedin_from_website_selenium("acme.com", company_name="Acme")

    assert result == "https://www.linkedin.com/company/acme"
    assert fake.requested == ["https://acme.com"]


def test_extract_returns_none_when_http_page_has_no_link(monkeypatch):
    _force_selenium_unavailable(monkeypatch)
    fake = _FakeClient(response=_FakeResponse(200, "<html><body>No links here</body></html>"))
    monkeypatch.setattr(scraping.httpx, "Client", lambda *args, **kwargs: fake)

    assert extract_linkedin_from_website_selenium("acme.com") is None


def test_extract_returns_none_when_http_request_raises(monkeypatch):
    _force_selenium_unavailable(monkeypatch)
    fake = _FakeClient(exc=RuntimeError("network unreachable"))
    monkeypatch.setattr(scraping.httpx, "Client", lambda *args, **kwargs: fake)

    assert extract_linkedin_from_website_selenium("acme.com") is None


def test_extract_ignores_non_ok_http_status(monkeypatch):
    _force_selenium_unavailable(monkeypatch)
    html = '<a href="https://www.linkedin.com/company/acme">Acme</a>'
    fake = _FakeClient(response=_FakeResponse(500, html))
    monkeypatch.setattr(scraping.httpx, "Client", lambda *args, **kwargs: fake)

    assert extract_linkedin_from_website_selenium("acme.com") is None
