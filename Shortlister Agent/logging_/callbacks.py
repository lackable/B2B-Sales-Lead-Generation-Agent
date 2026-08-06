"""
PipelineLogger — LangChain BaseCallbackHandler for the Shortlister Agent.

Captures every LLM start/end, tool start/end/error, and chain start/end event
and routes them through the shared structured logger (or the LogStore fallback).
All print() calls have been replaced with logger.event() / logger.warning().
"""

import time
import tiktoken
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

import config
from .log_store import LogStore


class PipelineLogger(BaseCallbackHandler):
    def __init__(self, session_id: str):
        super().__init__()
        self.log_store = LogStore(run_id=session_id)
        self.start_times: Dict[UUID, float] = {}
        self.run_input_tokens: Dict[UUID, int] = {}
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    # ── Internal helpers ────────────────────────────────────────────────────

    def _emit(self, event_type: str, data: dict, level: str = "info") -> None:
        """Route event through structured logger if available, else LogStore."""
        try:
            from logging_utils.registry import emit_event
            if emit_event(event_type, data, level=level, component="logging_.callbacks"):
                return
        except Exception:
            pass
        self.log_store.write_event(event_type, data)

    # ── LLM callbacks ───────────────────────────────────────────────────────

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

        generation = ""
        if response.generations and response.generations[0]:
            gen_obj = response.generations[0][0]
            generation = getattr(gen_obj, "text", "") or ""
            if not generation and hasattr(gen_obj, "message") and hasattr(gen_obj.message, "content"):
                generation = str(gen_obj.message.content or "")

        response_preview = generation[:1000] + "..." if len(generation) > 1000 else generation

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
            "reasoning_tokens_api": token_usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0),
            "calculated_output_tokens": calculated_output_tokens,
            "response_preview": response_preview,
            "latency_ms": latency_ms,
        })

    # ── Tool callbacks ──────────────────────────────────────────────────────

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

        # Detect contact_found pattern (LinkedIn personal URL in tool output)
        import re
        li_urls = re.findall(r'https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9\-_%]+', output_str, re.IGNORECASE)

        self._emit("tool_end", {
            "callback_run_id": str(run_id),
            "callback_parent_run_id": str(parent_run_id) if parent_run_id else None,
            "tool_output_preview": preview,
            "latency_ms": latency_ms,
        })

        if li_urls:
            self._emit("contact_found", {
                "linkedin_url": li_urls[0],
                "source": "tool_output",
            })

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

    # ── Chain callbacks ─────────────────────────────────────────────────────

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

    # ── Token summary ───────────────────────────────────────────────────────

    def get_token_usage_summary(self) -> dict:
        total_tokens = self.total_prompt_tokens + self.total_completion_tokens
        cost_input = (self.total_prompt_tokens / 1_000_000) * getattr(config, "PER_MILLION_INPUT_TK_COST", 0.150)
        cost_output = (self.total_completion_tokens / 1_000_000) * getattr(config, "PER_MILLION_OUTPUT_TK_COST", 0.600)
        total_cost = cost_input + cost_output
        return {
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": total_tokens,
            "cost_input": cost_input,
            "cost_output": cost_output,
            "total_cost": total_cost,
        }
