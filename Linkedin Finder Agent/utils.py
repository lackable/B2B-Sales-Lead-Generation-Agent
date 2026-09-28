"""Utility functions and helpers for the Contact Finder agent."""

import asyncio
import logging
from datetime import datetime
from typing import List, Any

from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI

import config as env_config
from mcp_client.bright_data_client import get_bright_data_tools
from logging_ import log_print

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

MAX_MESSAGE_CONTENT_CHARS = 500_000   # Cap single message content at 500k chars (~125k tokens)
MAX_TOOL_OUTPUT_CHARS     = 40_000    # Cap individual tool outputs at 40k chars (~10k tokens) to prevent API stalls

def truncate_tool_output(obs: Any, max_chars: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    """Truncate tool observation strings to prevent oversized API payloads."""
    obs_str = str(obs) if obs is not None else ""
    if len(obs_str) > max_chars:
        return obs_str[:max_chars] + f"\n\n[Warning: Tool output truncated from {len(obs_str)} to {max_chars} characters to fit API payload limits.]"
    return obs_str

def sanitize_input_messages(input_data: Any, max_chars: int = MAX_MESSAGE_CONTENT_CHARS):
    """Sanitize message objects or lists of messages to ensure no content exceeds length limit."""
    if isinstance(input_data, list):
        sanitized = []
        for msg in input_data:
            if hasattr(msg, "content") and isinstance(msg.content, str) and len(msg.content) > max_chars:
                truncated_text = msg.content[:max_chars] + f"\n\n[Warning: Message content truncated from {len(msg.content)} to {max_chars} characters to satisfy API limits.]"
                msg_copy = msg.model_copy(update={"content": truncated_text}) if hasattr(msg, "model_copy") else msg
                sanitized.append(msg_copy)
            else:
                sanitized.append(msg)
        return sanitized
    elif hasattr(input_data, "content") and isinstance(input_data.content, str) and len(input_data.content) > max_chars:
        truncated_text = input_data.content[:max_chars] + f"\n\n[Warning: Message content truncated from {len(input_data.content)} to {max_chars} characters to satisfy API limits.]"
        return input_data.model_copy(update={"content": truncated_text}) if hasattr(input_data, "model_copy") else input_data
    return input_data

async def invoke_model_with_rate_limit_retry(model_or_factory, input_data, max_retries: int = 5, sleep_seconds: int = None):
    """
    Invokes a LangChain model/runnable with automatic fallback on RateLimitError (429) or Timeout.
    If a rate limit or timeout occurs:
      1. Switches deployment name (e.g. from 'gpt-5-mini-2' to 'gpt-5.4-mini').
      2. If all deployments hit limits (full cycle), waits 65s before switching back.
      3. Retries on the new deployment.
    """
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
            is_timeout = "timeout" in err_str or "timed out" in err_str or "connection" in err_str or "readtimeout" in err_str
            
            if (is_rate_limit or is_timeout) and attempt < max_retries:
                new_dep, is_full_cycle, prev_dep = await deployment_manager.switch_deployment()
                reason = "Rate limit" if is_rate_limit else "Request timeout"
                if is_full_cycle:
                    log_print(f"⚠️ {reason} hit on deployment '{prev_dep}'. All deployments exhausted. Waiting {sleep_seconds}s before switching back to '{new_dep}' (Attempt {attempt+1}/{max_retries})...")
                    await asyncio.sleep(sleep_seconds)
                else:
                    log_print(f"⚠️ {reason} hit on deployment '{prev_dep}'. Switching immediately to deployment '{new_dep}' (Attempt {attempt+1}/{max_retries})...")
            else:
                raise e

def get_today_str() -> str:
    """Get the current date as a string."""
    return datetime.now().strftime("%Y-%m-%d")
