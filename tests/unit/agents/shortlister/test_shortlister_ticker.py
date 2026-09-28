"""Hermetic unit tests for ticker helpers and the financedatabase website fallback."""

import pandas as pd
import pytest

from leadgen.agents.shortlister import ticker
from leadgen.agents.shortlister.ticker import (
    convert_ticker,
    fallback_financedatabase_website,
    get_financedatabase_equities,
)

# ── convert_ticker (existing coverage kept) ───────────────────────────────────


def test_convert_ticker_nse():
    yahoo_ticker, symbol, suffix = convert_ticker("NSE:TCS")
    assert yahoo_ticker == "TCS.NS"
    assert symbol == "TCS"
    assert suffix == ".NS"


def test_convert_ticker_bse():
    yahoo_ticker, symbol, suffix = convert_ticker("BSE:TCS")
    assert yahoo_ticker == "TCS.BO"
    assert symbol == "TCS"
    assert suffix == ".BO"


def test_convert_ticker_none_and_empty():
    assert convert_ticker(None) == ("", "", "")
    assert convert_ticker("") == ("", "", "")


# ── get_financedatabase_equities ──────────────────────────────────────────────


def test_get_financedatabase_equities_caches_result(monkeypatch):
    monkeypatch.setattr(ticker, "_india_equities", None)
    import financedatabase

    sentinel = pd.DataFrame({"website": ["https://acme.com"]}, index=["ACME.NS"])
    calls = {"count": 0}

    class _FakeEquities:
        def select(self, country):
            calls["count"] += 1
            assert country == "India"
            return sentinel

    monkeypatch.setattr(financedatabase, "Equities", lambda: _FakeEquities())

    first = get_financedatabase_equities()
    second = get_financedatabase_equities()

    assert first is sentinel
    assert second is sentinel
    assert calls["count"] == 1
    assert ticker._india_equities is sentinel


def test_get_financedatabase_equities_returns_empty_dict_on_failure(monkeypatch):
    monkeypatch.setattr(ticker, "_india_equities", None)
    import financedatabase

    def _boom():
        raise RuntimeError("financedatabase unavailable")

    monkeypatch.setattr(financedatabase, "Equities", _boom)

    assert get_financedatabase_equities() == {}
    assert ticker._india_equities == {}


def test_get_financedatabase_equities_returns_empty_dict_on_select_failure(monkeypatch):
    monkeypatch.setattr(ticker, "_india_equities", None)
    import financedatabase

    class _FailingEquities:
        def select(self, country):  # pragma: no cover - exercised via exception
            raise RuntimeError("select exploded")

    monkeypatch.setattr(financedatabase, "Equities", lambda: _FailingEquities())

    assert get_financedatabase_equities() == {}


# ── fallback_financedatabase_website ──────────────────────────────────────────


def test_fallback_website_primary_ticker_hit(monkeypatch):
    frame = pd.DataFrame({"website": ["https://acme-primary.com"]}, index=["ACME.NS"])
    monkeypatch.setattr(ticker, "get_financedatabase_equities", lambda: frame)

    assert fallback_financedatabase_website("NSE:ACME") == "https://acme-primary.com"


def test_fallback_website_alternate_exchange_suffix_hit(monkeypatch):
    frame = pd.DataFrame({"website": ["https://acme-bse.com"]}, index=["ACME.BO"])
    monkeypatch.setattr(ticker, "get_financedatabase_equities", lambda: frame)

    assert fallback_financedatabase_website("NSE:ACME") == "https://acme-bse.com"


def test_fallback_website_not_found_value_returns_none(monkeypatch):
    frame = pd.DataFrame({"website": ["not found"]}, index=["ACME.NS"])
    monkeypatch.setattr(ticker, "get_financedatabase_equities", lambda: frame)

    assert fallback_financedatabase_website("NSE:ACME") is None


def test_fallback_website_strips_whitespace(monkeypatch):
    frame = pd.DataFrame({"website": ["  https://acme.com  "]}, index=["ACME.NS"])
    monkeypatch.setattr(ticker, "get_financedatabase_equities", lambda: frame)

    assert fallback_financedatabase_website("NSE:ACME") == "https://acme.com"


def test_fallback_website_empty_or_none_dataframe(monkeypatch):
    monkeypatch.setattr(ticker, "get_financedatabase_equities", lambda: pd.DataFrame())
    assert fallback_financedatabase_website("NSE:ACME") is None

    monkeypatch.setattr(ticker, "get_financedatabase_equities", lambda: None)
    assert fallback_financedatabase_website("NSE:ACME") is None


def test_fallback_website_exception_returns_none(monkeypatch):
    def _boom():
        raise RuntimeError("lookup exploded")

    monkeypatch.setattr(ticker, "get_financedatabase_equities", _boom)

    assert fallback_financedatabase_website("NSE:ACME") is None


def test_fallback_website_non_string_or_empty_ticker_returns_none(monkeypatch):
    frame = pd.DataFrame({"website": ["https://acme.com"]}, index=["ACME.NS"])
    monkeypatch.setattr(ticker, "get_financedatabase_equities", lambda: frame)

    assert fallback_financedatabase_website("") is None
    assert fallback_financedatabase_website(None) is None
    assert fallback_financedatabase_website(123) is None


def test_convert_ticker_unknown_exchange_defaults_to_bse():
    yahoo_ticker, symbol, suffix = convert_ticker("NASDAQ:ACME")
    assert yahoo_ticker == "ACME.BO"
    assert symbol == "ACME"
    assert suffix == ".BO"


@pytest.mark.parametrize("raw", ["", None])
def test_convert_ticker_invalid_inputs(raw):
    assert convert_ticker(raw) == ("", "", "")
