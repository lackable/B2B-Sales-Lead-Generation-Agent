"""Utility functions and helpers for Shortlister Agent."""

import asyncio
from datetime import datetime
from typing import List, Optional

from langchain_core.messages import BaseMessage, AIMessage, filter_messages
from langchain_core.tools import tool, BaseTool
from langchain_openai import ChatOpenAI

import config as env_config
from mcp_client.bright_data_client import get_bright_data_tools


def _emit(event_type: str, data: dict, level: str = "info") -> None:
    """Emit structured event via shared pipeline logger if available."""
    try:
        from logging_utils.registry import emit_event
        emit_event(event_type, data, level=level, component="utils")
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

class DeploymentManager:
    """Thread-safe manager for cycling through the configured model fallback names."""
    def __init__(self, deployments: List[str] = None):
        self.deployments = deployments or env_config.OPENAI_MODELS
        self.current_index = 0
        self._lock = asyncio.Lock()

    def get_current_deployment(self) -> str:
        return self.deployments[self.current_index] if self.deployments else ""

    async def switch_deployment(self) -> tuple[str, bool, str]:
        async with self._lock:
            if not self.deployments:
                return "", True, ""
            prev_deployment = self.deployments[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.deployments)
            new_deployment = self.deployments[self.current_index]
            is_full_cycle = (self.current_index == 0)
            return new_deployment, is_full_cycle, prev_deployment

# Global singleton deployment manager instance
deployment_manager = DeploymentManager()

def get_chat_model(deployment_name: str = None, max_retries: int = 3, timeout: float = 90.0):
    """Helper to instantiate ChatOpenAI against the configured OpenAI-compatible endpoint."""
    base_url = env_config.OPENAI_BASE_URL
    api_key = env_config.OPENAI_API_KEY
    target_deployment = deployment_name or deployment_manager.get_current_deployment()
    if not (base_url and api_key and target_deployment):
        raise RuntimeError(
            "LLM not configured: set OPENAI_BASE_URL, OPENAI_API_KEY and "
            "OPENAI_MODEL (or OPENAI_MODELS) in the repo-root .env"
        )
    return ChatOpenAI(
        model=target_deployment,
        api_key=api_key,
        base_url=base_url,
        temperature=0.0,
        max_retries=max_retries,
        request_timeout=timeout,
        timeout=timeout
    )

MAX_MESSAGE_CONTENT_CHARS = 500_000
MAX_TOOL_OUTPUT_CHARS     = 40_000

def truncate_tool_output(obs, max_chars: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    """Truncate tool observation strings to prevent oversized API payloads."""
    obs_str = str(obs) if obs is not None else ""
    if len(obs_str) > max_chars:
        return obs_str[:max_chars] + f"\n\n[Warning: Tool output truncated from {len(obs_str)} to {max_chars} characters to fit API payload limits.]"
    return obs_str

def sanitize_input_messages(input_data, max_chars: int = MAX_MESSAGE_CONTENT_CHARS):
    """Sanitize message content length."""
    if isinstance(input_data, list):
        sanitized = []
        for msg in input_data:
            if hasattr(msg, "content") and isinstance(msg.content, str) and len(msg.content) > max_chars:
                truncated_text = msg.content[:max_chars] + f"\n\n[Warning: Content truncated]"
                msg_copy = msg.model_copy(update={"content": truncated_text}) if hasattr(msg, "model_copy") else msg
                sanitized.append(msg_copy)
            else:
                sanitized.append(msg)
        return sanitized
    elif hasattr(input_data, "content") and isinstance(input_data.content, str) and len(input_data.content) > max_chars:
        truncated_text = input_data.content[:max_chars] + f"\n\n[Warning: Content truncated]"
        return input_data.model_copy(update={"content": truncated_text}) if hasattr(input_data, "model_copy") else input_data
    return input_data

async def invoke_model_with_rate_limit_retry(model_or_factory, input_data, max_retries: int = 5, sleep_seconds: int = None):
    """Invokes a model with automatic deployment fallback on 429 / timeout."""
    if sleep_seconds is None:
        sleep_seconds = getattr(env_config, "RATE_LIMIT_CYCLE_WAIT_SECONDS", 65)

    sanitized_data = sanitize_input_messages(input_data)

    for attempt in range(max_retries + 1):
        current_dep = deployment_manager.get_current_deployment()
        
        if callable(model_or_factory):
            active_model = model_or_factory(current_dep)
        else:
            active_model = model_or_factory
            
        try:
            return await active_model.ainvoke(sanitized_data)
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = "429" in err_str or "rate_limit" in err_str or "too_many_requests" in err_str
            is_timeout = "timeout" in err_str or "timed out" in err_str or "connection" in err_str
            
            if (is_rate_limit or is_timeout) and attempt < max_retries:
                new_dep, is_full_cycle, prev_dep = await deployment_manager.switch_deployment()
                reason = "Rate limit" if is_rate_limit else "Request timeout"
                if is_full_cycle:
                    _emit("progress", {"stage": "rate_limit", "message": f"{reason} on '{prev_dep}'. Exhausted all deployments. Waiting {sleep_seconds}s..."}, level="warning")
                    print(f"⚠️ {reason} hit on deployment '{prev_dep}'. Exhausted all deployments. Waiting {sleep_seconds}s...")
                    await asyncio.sleep(sleep_seconds)
                else:
                    _emit("progress", {"stage": "rate_limit", "message": f"{reason} on '{prev_dep}'. Switching to '{new_dep}'..."}, level="warning")
                    print(f"⚠️ {reason} hit on deployment '{prev_dep}'. Switching to '{new_dep}'...")
            else:
                raise e

def get_today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def remove_up_to_last_ai_message(messages: List[BaseMessage]) -> List[BaseMessage]:
    last_ai_idx = -1
    for i, msg in enumerate(messages):
        if isinstance(msg, AIMessage):
            last_ai_idx = i
            
    if last_ai_idx > 0:
        return [messages[0]] + messages[last_ai_idx:]
    return messages

def is_token_limit_exceeded(error: Exception, model_name: str) -> bool:
    error_str = str(error).lower()
    return "token limit" in error_str or "context length" in error_str

def get_model_token_limit(model_name: str) -> int:
    if not model_name:
        return 8192
    if "gpt-5" in model_name or "gpt-4o" in model_name:
        return 128000
    return 8192

@tool(description="Strategic reflection tool for verification planning")
def think_tool(reflection: str) -> str:
    """Tool for strategic reflection during research/verification."""
    return f"Reflection recorded: {reflection}"

async def get_all_tools() -> List[BaseTool]:
    try:
        mcp_tools = await get_bright_data_tools()
        if not mcp_tools:
            _emit("mcp_error", {"server": "bright_data", "error": "No MCP tools available"}, level="error")
            raise RuntimeError("MCP Failed: No MCP tools available.")
        _emit("mcp_connect", {"server": "bright_data", "tool_count": len(mcp_tools)})
        return mcp_tools + [think_tool]
    except Exception as e:
        if not str(e).startswith("MCP Failed"):
            _emit("mcp_error", {"server": "bright_data", "error": str(e)}, level="error")
            raise RuntimeError(f"MCP Failed: {e}") from e
        raise
