"""TradingView → Yahoo Finance ticker helpers and the financedatabase website fallback."""

from typing import Optional

from leadgen.core.telemetry.registry import emit_event


def _emit(event_type: str, data: dict, level: str = "info") -> None:
    """Emit structured event via shared pipeline logger if available."""
    try:
        emit_event(event_type, data, level=level, component="agents.shortlister.ticker")
    except Exception:
        pass


# Singleton lazy-loaded financedatabase equities cache
_india_equities = None


def get_financedatabase_equities():
    global _india_equities
    if _india_equities is None:
        try:
            import financedatabase as fd
            equities = fd.Equities()
            _india_equities = equities.select(country='India')
        except Exception as e:
            _emit("mcp_error", {"server": "financedatabase", "error": str(e)}, level="warning")
            _india_equities = {}
    return _india_equities


def convert_ticker(ticker_str: str) -> tuple[str, str, str]:
    """
    Converts TradingView ticker format (e.g. NSE:TCS, BSE:TCS) into Yahoo Finance ticker format.
    Returns: (yahoo_ticker, symbol, exchange_suffix)
    """
    if not ticker_str or not isinstance(ticker_str, str):
        return "", "", ""
    if ':' in ticker_str:
        exchange, symbol = ticker_str.split(':', 1)
        suffix = '.NS' if exchange.upper() == 'NSE' else '.BO'
    else:
        symbol = ticker_str
        suffix = '.NS'
    return symbol + suffix, symbol, suffix


def fallback_financedatabase_website(ticker_str: str) -> Optional[str]:
    """
    Fallback website lookup using financedatabase if yfinance misses the website field.
    Reused logic from market_cap_tradingview_test_v2.py.
    """
    try:
        if not ticker_str or not isinstance(ticker_str, str):
            return None
        equities_df = get_financedatabase_equities()
        if equities_df is None or len(equities_df) == 0:
            return None

        yahoo_ticker, symbol, suffix = convert_ticker(ticker_str)
        if not yahoo_ticker:
            return None

        if hasattr(equities_df, 'index') and yahoo_ticker in equities_df.index:
            site = equities_df.loc[yahoo_ticker, 'website']
            if isinstance(site, str) and site.strip() and site.strip().lower() != 'not found':
                return site.strip()

        # Try alternate exchange suffix
        alt_suffix = '.BO' if suffix == '.NS' else '.NS'
        alt_ticker = symbol + alt_suffix
        if hasattr(equities_df, 'index') and alt_ticker in equities_df.index:
            site = equities_df.loc[alt_ticker, 'website']
            if isinstance(site, str) and site.strip() and site.strip().lower() != 'not found':
                return site.strip()
    except Exception as e:
        _emit("mcp_error", {"server": "financedatabase", "error": str(e), "ticker": ticker_str}, level="warning")
    return None
