"""Unit tests for leadgen.core.telemetry.callbacks."""

import logging
import re
from types import SimpleNamespace
from uuid import uuid4

import pytest
import tiktoken
from langchain_core.outputs import Generation, LLMResult

from leadgen import config
from leadgen.core.telemetry import registry
from leadgen.core.telemetry.callbacks import PipelineLogger, log_print

_TIMESTAMP = r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]"
_ENCODING = tiktoken.get_encoding("cl100k_base")


class CapturingLogger:
    def __init__(self):
        self.events = []

    def event(self, event_type, data, **kwargs):
        self.events.append({"event_type": event_type, "data": dict(data), **kwargs})


@pytest.fixture
def capture():
    previous = registry.get_logger()
    logger = CapturingLogger()
    registry.register_logger(logger)
    yield logger
    registry.register_logger(previous)


@pytest.fixture
def pipeline_logger(capture, isolated_var):
    return PipelineLogger(session_id="run-1")


# ── log_print ────────────────────────────────────────────────────────────────


def test_log_print_prefixes_timestamp(capsys):
    log_print("hello")
    out = capsys.readouterr().out
    assert re.fullmatch(_TIMESTAMP + r" hello\n", out)


def test_log_print_handles_leading_newline(capsys):
    log_print("\nhello")
    out = capsys.readouterr().out
    assert re.fullmatch(r"\n" + _TIMESTAMP + r" hello\n", out)


def test_log_print_forwards_extra_args(capsys):
    log_print("a", "b", 1)
    out = capsys.readouterr().out
    assert re.fullmatch(_TIMESTAMP + r" a b 1\n", out)


def test_log_print_handles_non_string_first_arg(capture, capsys):
    # A non-string first arg is treated as an empty message (and not printed).
    log_print(123)
    out = capsys.readouterr().out
    assert re.fullmatch(_TIMESTAMP + r" \n", out)
    assert capture.events[0]["data"] == {"message": ""}


def test_log_print_emits_log_event(capture, capsys):
    log_print("hello")
    capsys.readouterr()
    assert capture.events == [
        {
            "event_type": "log",
            "data": {"message": "hello"},
            "level": logging.INFO,
            "component": "core.telemetry.log_print",
        }
    ]


def test_log_print_event_message_includes_newline(capture, capsys):
    log_print("\nhello")
    capsys.readouterr()
    assert capture.events[0]["data"] == {"message": "\nhello"}


def test_log_print_never_raises_when_logging_unavailable(monkeypatch, capsys):
    def _boom(*args, **kwargs):
        raise RuntimeError("logging down")

    monkeypatch.setattr(registry, "emit_event", _boom)

    log_print("still works")
    assert "still works" in capsys.readouterr().out


# ── PipelineLogger: LLM callbacks ────────────────────────────────────────────


def test_on_llm_start_records_calculated_tokens(pipeline_logger, capture):
    run_id = uuid4()
    pipeline_logger.on_llm_start({}, ["hello world"], run_id=run_id, tags=["t"], metadata={"m": 1})

    expected = len(_ENCODING.encode("hello world"))
    assert expected == 2
    assert pipeline_logger.run_input_tokens[run_id] == expected
    assert pipeline_logger.total_prompt_tokens == expected
    assert run_id in pipeline_logger.start_times

    event = capture.events[-1]
    assert event["event_type"] == "llm_start"
    assert event["data"] == {
        "callback_run_id": str(run_id),
        "callback_parent_run_id": None,
        "model_name": "unknown",
        "prompt_preview": "hello world",
        "calculated_input_tokens": expected,
        "tags": ["t"],
        "metadata": {"m": 1},
    }


def test_on_llm_start_truncates_long_prompt(pipeline_logger, capture):
    pipeline_logger.on_llm_start({}, ["x" * 600], run_id=uuid4())
    assert capture.events[-1]["data"]["prompt_preview"] == "x" * 500 + "..."


def test_on_llm_start_with_empty_prompts(pipeline_logger, capture):
    run_id = uuid4()
    pipeline_logger.on_llm_start({}, [], run_id=run_id)
    assert pipeline_logger.run_input_tokens[run_id] == 0
    assert capture.events[-1]["data"]["calculated_input_tokens"] == 0
    assert capture.events[-1]["data"]["prompt_preview"] == ""


def test_on_llm_start_uses_invocation_params_model_name(pipeline_logger, capture):
    pipeline_logger.on_llm_start({}, ["hi"], run_id=uuid4(), invocation_params={"model_name": "gpt-3.5-turbo"})
    assert capture.events[-1]["data"]["model_name"] == "gpt-3.5-turbo"


def test_on_llm_end_uses_api_tokens_over_calculated(pipeline_logger, capture):
    run_id = uuid4()
    pipeline_logger.on_llm_start({}, ["hello world"], run_id=run_id)
    assert pipeline_logger.total_prompt_tokens == 2

    response = LLMResult(
        generations=[[Generation(text="hi there")]],
        llm_output={"token_usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}},
    )
    pipeline_logger.on_llm_end(response, run_id=run_id)

    assert pipeline_logger.total_prompt_tokens == 100
    assert pipeline_logger.total_completion_tokens == 50
    assert run_id not in pipeline_logger.start_times
    assert run_id not in pipeline_logger.run_input_tokens

    event = capture.events[-1]
    assert event["event_type"] == "llm_end"
    assert event["data"]["prompt_tokens_api"] == 100
    assert event["data"]["completion_tokens_api"] == 50
    assert event["data"]["total_tokens_api"] == 150
    assert event["data"]["calculated_output_tokens"] == len(_ENCODING.encode("hi there"))
    assert event["data"]["response_preview"] == "hi there"
    assert isinstance(event["data"]["latency_ms"], int)


def test_on_llm_end_falls_back_to_calculated_output_tokens(pipeline_logger, capture):
    run_id = uuid4()
    pipeline_logger.on_llm_start({}, ["hello world"], run_id=run_id)

    response = LLMResult(generations=[[Generation(text="hello world")]], llm_output=None)
    pipeline_logger.on_llm_end(response, run_id=run_id)

    expected = len(_ENCODING.encode("hello world"))
    assert pipeline_logger.total_completion_tokens == expected
    assert pipeline_logger.total_prompt_tokens == expected
    assert capture.events[-1]["data"]["calculated_output_tokens"] == expected


def test_on_llm_end_without_start_has_no_latency(pipeline_logger, capture):
    run_id = uuid4()
    response = LLMResult(generations=[[Generation(text="x")]], llm_output=None)
    pipeline_logger.on_llm_end(response, run_id=run_id)

    assert capture.events[-1]["data"]["latency_ms"] is None
    assert pipeline_logger.run_input_tokens.get(run_id) is None


def test_on_llm_end_reads_message_content_when_no_text(pipeline_logger, capture):
    generation = SimpleNamespace(text="", message=SimpleNamespace(content="from message"))
    response = SimpleNamespace(generations=[[generation]], llm_output={})

    pipeline_logger.on_llm_end(response, run_id=uuid4())
    assert capture.events[-1]["data"]["response_preview"] == "from message"


def test_on_llm_end_handles_empty_generations(pipeline_logger, capture):
    response = LLMResult(generations=[], llm_output=None)
    pipeline_logger.on_llm_end(response, run_id=uuid4())

    assert capture.events[-1]["data"]["response_preview"] == ""
    assert capture.events[-1]["data"]["calculated_output_tokens"] == 0


def test_on_llm_end_truncates_long_response(pipeline_logger, capture):
    response = LLMResult(generations=[[Generation(text="y" * 1500)]], llm_output=None)
    pipeline_logger.on_llm_end(response, run_id=uuid4())

    preview = capture.events[-1]["data"]["response_preview"]
    assert preview == "y" * 1000 + "..."
    assert len(preview) == 1003


# ── PipelineLogger: tool callbacks ───────────────────────────────────────────


def test_on_tool_start_emits_event(pipeline_logger, capture):
    run_id = uuid4()
    pipeline_logger.on_tool_start({"name": "search"}, "query", run_id=run_id, tags=["t"], metadata={"m": 1})

    assert run_id in pipeline_logger.start_times
    assert capture.events[-1] == {
        "event_type": "tool_start",
        "data": {
            "callback_run_id": str(run_id),
            "callback_parent_run_id": None,
            "tool_name": "search",
            "tool_input": "query",
            "tags": ["t"],
            "metadata": {"m": 1},
        },
        "level": logging.INFO,
        "component": "core.telemetry.callbacks",
    }


def test_on_tool_start_defaults_tool_name(pipeline_logger, capture):
    pipeline_logger.on_tool_start({}, "q", run_id=uuid4())
    assert capture.events[-1]["data"]["tool_name"] == "unknown"


def test_on_tool_end_emits_tool_end_with_latency(pipeline_logger, capture):
    run_id = uuid4()
    pipeline_logger.on_tool_start({"name": "t"}, "in", run_id=run_id)
    pipeline_logger.on_tool_end("result", run_id=run_id)

    event = capture.events[-1]
    assert event["event_type"] == "tool_end"
    assert event["data"]["tool_output_preview"] == "result"
    assert isinstance(event["data"]["latency_ms"], int)
    assert run_id not in pipeline_logger.start_times


def test_on_tool_end_truncates_preview_at_1000_chars(pipeline_logger, capture):
    pipeline_logger.on_tool_end("z" * 1500, run_id=uuid4())
    preview = capture.events[-1]["data"]["tool_output_preview"]
    assert preview == "z" * 1000 + "..."
    assert len(preview) == 1003


def test_on_tool_end_emits_contact_found_for_linkedin_url(pipeline_logger, capture):
    pipeline_logger.on_tool_end("Profile: https://www.linkedin.com/in/john-doe-123 done", run_id=uuid4())

    assert [event["event_type"] for event in capture.events] == ["tool_end", "contact_found"]
    assert capture.events[-1]["data"] == {
        "linkedin_url": "https://www.linkedin.com/in/john-doe-123",
        "source": "tool_output",
    }


def test_on_tool_end_without_url_emits_only_tool_end(pipeline_logger, capture):
    pipeline_logger.on_tool_end("no links here", run_id=uuid4())
    assert [event["event_type"] for event in capture.events] == ["tool_end"]


def test_on_tool_error_emits_warning_event(pipeline_logger, capture):
    run_id = uuid4()
    pipeline_logger.on_tool_start({"name": "t"}, "in", run_id=run_id)
    pipeline_logger.on_tool_error(ValueError("bad"), run_id=run_id)

    event = capture.events[-1]
    assert event["event_type"] == "tool_error"
    assert event["level"] == logging.WARNING
    assert event["data"]["error"] == "bad"
    assert isinstance(event["data"]["latency_ms"], int)
    assert run_id not in pipeline_logger.start_times


# ── PipelineLogger: chain callbacks ──────────────────────────────────────────


def test_on_chain_callbacks_emit_events(pipeline_logger, capture):
    run_id = uuid4()
    pipeline_logger.on_chain_start({"name": "chain"}, {"in": 1}, run_id=run_id, tags=["t"], metadata={"m": 1})
    pipeline_logger.on_chain_end({"out": 2}, run_id=run_id)

    first, second = capture.events
    assert first["event_type"] == "chain_start"
    assert first["data"] == {
        "callback_run_id": str(run_id),
        "callback_parent_run_id": None,
        "chain_name": "chain",
        "tags": ["t"],
        "metadata": {"m": 1},
    }
    assert second["event_type"] == "chain_end"
    assert second["data"] == {"callback_run_id": str(run_id), "callback_parent_run_id": None}


def test_on_chain_start_defaults_chain_name(pipeline_logger, capture):
    pipeline_logger.on_chain_start(None, {}, run_id=uuid4())
    assert capture.events[-1]["data"]["chain_name"] == "unknown"


# ── PipelineLogger: token summary ────────────────────────────────────────────


def test_get_token_usage_summary_cost_math(pipeline_logger, monkeypatch):
    monkeypatch.setattr(config, "PER_MILLION_INPUT_TK_COST", 3.0)
    monkeypatch.setattr(config, "PER_MILLION_OUTPUT_TK_COST", 15.0)
    pipeline_logger.total_prompt_tokens = 1_000_000
    pipeline_logger.total_completion_tokens = 500_000

    summary = pipeline_logger.get_token_usage_summary()

    assert summary == {
        "total_prompt_tokens": 1_000_000,
        "total_completion_tokens": 500_000,
        "total_tokens": 1_500_000,
        "cost_input": pytest.approx(3.0),
        "cost_output": pytest.approx(7.5),
        "total_cost": pytest.approx(10.5),
    }


def test_get_token_usage_summary_uses_config_costs(pipeline_logger, monkeypatch):
    monkeypatch.setattr(config, "PER_MILLION_INPUT_TK_COST", 1.0)
    monkeypatch.setattr(config, "PER_MILLION_OUTPUT_TK_COST", 4.0)
    pipeline_logger.total_prompt_tokens = 2_000_000
    pipeline_logger.total_completion_tokens = 250_000

    summary = pipeline_logger.get_token_usage_summary()

    assert summary["total_tokens"] == 2_250_000
    assert summary["cost_input"] == pytest.approx(2.0)
    assert summary["cost_output"] == pytest.approx(1.0)
    assert summary["total_cost"] == pytest.approx(3.0)
