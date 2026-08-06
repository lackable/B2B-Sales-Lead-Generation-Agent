"""
PipelineLogger — LangChain BaseCallbackHandler for LinkedIn Finder Agent.

Identical contract to Shortlister's callbacks.py but uses LinkedIn agent's
log_store shim. All print() calls replaced with structured logger events.
"""

import time
import tiktoken
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

import config
from .log_store import LogStore


def log_print(*args, **kwargs):
    """
    Backward-compatible print wrapper — keeps existing callers working.
    Also emits a structured 'log' event via the pipeline logger if available.
    """
    import sys
    from datetime import datetime
    ts = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    msg = args[0] if args and isinstance(args[0], str) else ""
    if msg.startswith("\n"):
        first_arg = f"\n{ts} {msg[1:]}"
    else:
        first_arg = f"{ts} {msg}"
    print(first_arg, *args[1:], **kwargs)
    sys.stdout.flush()

    # Also emit structured event
    try:
        from logging_utils.registry import emit_event
        emit_event("log", {"message": str(msg)}, component="logging_.log_print")
    except Exception:
        pass


class PipelineLogger(BaseCallbackHandler):
    def __init__(self, session_id: str):
        super().__init__()
        self.log_store = LogStore(run_id=session_id)
        self.start_times: Dict[UUID, float] = {}
        self.run_input_tokens: Dict[UUID, int] = {}
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def _emit(self, event_type: str, data: dict, level: str = "info") -> None:
        try:
            from logging_utils.registry import emit_event
            if emit_event(event_type, data, level=level, component="logging_.callbacks"):
                return
        except Exception:
            pass
        self.log_store.write_event(event_type, data)

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], *,
        run_id: UUID, parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> Any:
        self.start_times[run_id] = time.time()
        model_name = kwargs.get("invocation_params", {}).get("model_name", "unknown")
        prompt_text = prompts[0] if prompts else ""
        prompt_preview = prompt_text[:500] + "..." if len(prompt_text) > 500 else prompt_text
        try:
            encoding = tiktoken.encoding_for_model(model_name)
        except Exception:
            encoding = tiktoken.get_encoding("cl100k_base")
        calculated_input_tokens = len(encoding.encode(prompt_text)) if prompt_text else 0
        self.run_input_tokens[run_id] = calculated_input_tokens
        self.total_prompt_tokens += calculated_input_tokens
        self._emit("llm_start", {
            "callback_run_id": str(run_id),
            "callback_parent_run_id": str(parent_run_id) if parent_run_id else None,
            "model_name": model_name,
            "prompt_preview": prompt_preview,
            "calculated_input_tokens": calculated_input_tokens,
            "tags": tags,
            "metadata": metadata,
        })

    def on_llm_end(
        self, response: LLMResult, *, run_id: UUID,
        parent_run_id: Optional[UUID] = None, **kwargs: Any
    ) -> Any:
        latency_ms = None
        if run_id in self.start_times:
            latency_ms = int((time.time() - self.start_times.pop(run_id)) * 1000)

        generation = response.generations[0][0].text if response.generations and response.generations[0] else ""
        response_preview = generation[:500] + "..." if len(generation) > 500 else generation

        llm_output = response.llm_output or {}
        token_usage = llm_output.get("token_usage") or {}
        api_prompt_tokens = token_usage.get("prompt_tokens") or token_usage.get("input_tokens")
        api_completion_tokens = token_usage.get("completion_tokens") or token_usage.get("output_tokens")

        try:
            encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            encoding = tiktoken.get_encoding("cl100k_base")
        calculated_output_tokens = len(encoding.encode(generation)) if generation else 0

        fallback_input = self.run_input_tokens.pop(run_id, 0)
        if api_completion_tokens is not None and api_completion_tokens > 0:
            self.total_completion_tokens += api_completion_tokens
            if api_prompt_tokens is not None and api_prompt_tokens > 0:
                self.total_prompt_tokens = max(0, self.total_prompt_tokens - fallback_input + api_prompt_tokens)
        else:
            self.total_completion_tokens += calculated_output_tokens

        self._emit("llm_end", {
            "callback_run_id": str(run_id),
            "callback_parent_run_id": str(parent_run_id) if parent_run_id else None,
            "completion_tokens_api": token_usage.get("completion_tokens", 0),
            "prompt_tokens_api": token_usage.get("prompt_tokens", 0),
            "total_tokens_api": token_usage.get("total_tokens", 0),
            "calculated_output_tokens": calculated_output_tokens,
            "response_preview": response_preview,
            "latency_ms": latency_ms,
        })

    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, *,
        run_id: UUID, parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> Any:
        self.start_times[run_id] = time.time()
        tool_name = serialized.get("name", "unknown")
        self._emit("tool_start", {
            "callback_run_id": str(run_id),
            "callback_parent_run_id": str(parent_run_id) if parent_run_id else None,
            "tool_name": tool_name,
            "tool_input": input_str,
            "tags": tags,
            "metadata": metadata,
        })

    def on_tool_end(
        self, output: Any, *, run_id: UUID,
        parent_run_id: Optional[UUID] = None, **kwargs: Any
    ) -> Any:
        latency_ms = None
        if run_id in self.start_times:
            latency_ms = int((time.time() - self.start_times.pop(run_id)) * 1000)
        output_str = str(output)
        preview = output_str[:1000] + "..." if len(output_str) > 1000 else output_str
        self._emit("tool_end", {
            "callback_run_id": str(run_id),
            "callback_parent_run_id": str(parent_run_id) if parent_run_id else None,
            "tool_output_preview": preview,
            "latency_ms": latency_ms,
        })

        import re
        li_urls = re.findall(r'https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9\-_%]+', output_str, re.IGNORECASE)
        if li_urls:
            self._emit("contact_found", {"linkedin_url": li_urls[0], "source": "tool_output"})

    def on_tool_error(
        self, error: Exception, *, run_id: UUID,
        parent_run_id: Optional[UUID] = None, **kwargs: Any
    ) -> Any:
        latency_ms = None
        if run_id in self.start_times:
            latency_ms = int((time.time() - self.start_times.pop(run_id)) * 1000)
        self._emit("tool_error", {
            "callback_run_id": str(run_id),
            "callback_parent_run_id": str(parent_run_id) if parent_run_id else None,
            "error": str(error),
            "latency_ms": latency_ms,
        }, level="warning")

    def on_chain_start(
        self, serialized: Dict[str, Any], inputs: Dict[str, Any], *,
        run_id: UUID, parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> Any:
        chain_name = (serialized or {}).get("name", "unknown")
        self._emit("chain_start", {
            "callback_run_id": str(run_id),
            "callback_parent_run_id": str(parent_run_id) if parent_run_id else None,
            "chain_name": chain_name,
            "tags": tags,
            "metadata": metadata,
        })

    def on_chain_end(
        self, outputs: Dict[str, Any], *, run_id: UUID,
        parent_run_id: Optional[UUID] = None, **kwargs: Any
    ) -> Any:
        self._emit("chain_end", {
            "callback_run_id": str(run_id),
            "callback_parent_run_id": str(parent_run_id) if parent_run_id else None,
        })

    def get_token_usage_summary(self) -> dict:
        total_tokens = self.total_prompt_tokens + self.total_completion_tokens
        cost_input = (self.total_prompt_tokens / 1_000_000) * getattr(config, "PER_MILLION_INPUT_TK_COST", 0.150)
        cost_output = (self.total_completion_tokens / 1_000_000) * getattr(config, "PER_MILLION_OUTPUT_TK_COST", 0.600)
        return {
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": total_tokens,
            "cost_input": cost_input,
            "cost_output": cost_output,
            "total_cost": cost_input + cost_output,
        }
