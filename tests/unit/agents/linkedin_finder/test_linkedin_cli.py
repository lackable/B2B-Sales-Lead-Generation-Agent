"""Unit tests for the LinkedIn Finder CLI entry point (``leadgen.agents.linkedin_finder.cli``)."""

import asyncio
import sys
from datetime import datetime

import pytest

from leadgen import config
from leadgen.agents.linkedin_finder import cli


class CapturingLogger:
    def __init__(self):
        self.events = []

    def event(self, event_type, data, **kwargs):
        self.events.append({"event_type": event_type, "data": dict(data), **kwargs})

    def types(self):
        return [event["event_type"] for event in self.events]


class FakePipelineLogger:
    instances = []

    def __init__(self, session_id):
        self.session_id = session_id
        self.log_store = type("Store", (), {"log_file": f"/tmp/run_{session_id}.jsonl"})()
        FakePipelineLogger.instances.append(self)

    def get_token_usage_summary(self):
        return {
            "total_prompt_tokens": 10,
            "total_completion_tokens": 5,
            "total_tokens": 15,
            "cost_input": 0.0000025,
            "cost_output": 0.00001,
            "total_cost": 0.0000125,
        }


class FakeGraph:
    def __init__(self):
        self.result = {"decision_makers": []}
        self.error = None
        self.calls = []

    async def ainvoke(self, state, config=None):
        self.calls.append({"state": state, "config": config})
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def cli_env(monkeypatch, isolated_var, capsys):
    FakePipelineLogger.instances.clear()

    logger = CapturingLogger()
    graph = FakeGraph()
    recorded = {"savers": [], "checkpoints": []}

    class FakeMemorySaver:
        def __init__(self):
            recorded["savers"].append(self)

    def fake_build_graph(checkpointer=None):
        recorded["checkpoints"].append(checkpointer)
        return graph

    monkeypatch.setattr(cli, "_bootstrap_logger", lambda session_id: logger)
    monkeypatch.setattr(cli, "PipelineLogger", FakePipelineLogger)
    monkeypatch.setattr(cli, "build_graph", fake_build_graph)
    monkeypatch.setattr("langgraph.checkpoint.memory.MemorySaver", FakeMemorySaver)

    return {
        "logger": logger,
        "graph": graph,
        "recorded": recorded,
        "out": lambda: capsys.readouterr().out,
        "argv": lambda *args: monkeypatch.setattr(sys, "argv", ["leadgen.agents.linkedin_finder", *args]),
    }


# ── _bootstrap_logger ──────────────────────────────────────────────────────────

def test_bootstrap_logger_binds_linkedin_agent(monkeypatch, isolated_var):
    seen = {}

    def fake_setup_logging(agent, run_id):
        seen.update({"agent": agent, "run_id": run_id})
        return "logger-sentinel"

    registered = []
    monkeypatch.setattr(cli, "setup_logging", fake_setup_logging)
    monkeypatch.setattr(cli, "set_logger", registered.append)

    result = cli._bootstrap_logger("session-abc")

    assert result == "logger-sentinel"
    assert seen == {"agent": "linkedin", "run_id": "session-abc"}
    assert registered == ["logger-sentinel"]


# ── run() ──────────────────────────────────────────────────────────────────────

def test_run_prepares_dirs_and_runs_main(monkeypatch, isolated_var):
    calls = []
    monkeypatch.setattr(config, "ensure_runtime_dirs", lambda: calls.append("dirs"))

    def fake_asyncio_run(coro):
        coro.close()  # never awaited on purpose — keep the warning out of the log
        calls.append("run")

    monkeypatch.setattr(asyncio, "run", fake_asyncio_run)

    async def fake_main():
        calls.append("main")

    monkeypatch.setattr(cli, "main", fake_main)

    cli.run()
    assert calls == ["dirs", "run"]


def test_run_installs_windows_selector_policy_only_on_win32(monkeypatch, isolated_var):
    applied = []
    monkeypatch.setattr(config, "ensure_runtime_dirs", lambda: None)

    def fake_asyncio_run(coro):
        coro.close()

    monkeypatch.setattr(asyncio, "run", fake_asyncio_run)
    monkeypatch.setattr(asyncio, "set_event_loop_policy", applied.append)

    monkeypatch.setattr(cli.sys, "platform", "win32")
    cli.run()
    assert len(applied) == 1

    applied.clear()
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    cli.run()
    assert applied == []


# ── main(): flag-driven run ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_main_runs_graph_from_flags(cli_env):
    cli_env["argv"](
        "--company_name", "Acme Ltd",
        "--company_website", "https://acme.example",
        "--company_linkedin", "https://linkedin.com/company/acme",
        "--location", "Pune, India",
    )
    cli_env["graph"].result = {
        "decision_makers": [
            {"name": "Asha Rao", "position": "CTO", "linkedin_url": "https://linkedin.com/in/asha"},
        ]
    }

    await cli.main()

    session_id = FakePipelineLogger.instances[0].session_id
    assert session_id.startswith("session-")
    datetime.strptime(session_id, "session-%Y%m%d-%H%M%S")

    call = cli_env["graph"].calls[0]
    assert call["state"] == {
        "company_name": "Acme Ltd",
        "company_linkedin": "https://linkedin.com/company/acme",
        "company_website": "https://acme.example",
        "location": "Pune, India",
        "generated_query": "",
        "serp_raw_response": {},
        "ai_overview": "",
        "decision_makers": [],
        "scrape_calls_used": 0,
        "loop_memory": [],
        "session_id": session_id,
    }
    assert call["config"]["configurable"] == {"thread_id": session_id}
    assert call["config"]["callbacks"] == [FakePipelineLogger.instances[0]]

    # the in-memory checkpointer is what gets handed to build_graph
    assert cli_env["recorded"]["checkpoints"] == cli_env["recorded"]["savers"]
    assert len(cli_env["recorded"]["savers"]) == 1

    assert cli_env["logger"].types() == ["pipeline_start", "pipeline_end"]
    start = cli_env["logger"].events[0]["data"]
    assert start == {
        "company_name": "Acme Ltd",
        "company_website": "https://acme.example",
        "location": "Pune, India",
        "session_id": session_id,
    }
    end = cli_env["logger"].events[1]["data"]
    assert end["company_name"] == "Acme Ltd"
    assert end["decision_makers_count"] == 1
    assert end["total_tokens"] == 15

    out = cli_env["out"]()
    assert "Starting pipeline for 'Acme Ltd'" in out
    assert "Acme Ltd is running" or "Starting pipeline" in out
    assert "Extracted 1 decision makers for Acme Ltd" in out
    assert "1. Asha Rao (CTO) -> https://linkedin.com/in/asha" in out
    assert f"Output Directory: {config.OUTPUT_DIR}" in out
    assert "Total Cost:    $0.000013" in out


@pytest.mark.asyncio
async def test_main_honours_explicit_session_id(cli_env):
    cli_env["argv"]("--company_name", "Acme Ltd", "--session_id", "Acme-session-1")

    await cli.main()

    assert FakePipelineLogger.instances[0].session_id == "Acme-session-1"
    assert cli_env["graph"].calls[0]["config"]["configurable"] == {"thread_id": "Acme-session-1"}


@pytest.mark.asyncio
async def test_main_defaults_blank_location_to_india(cli_env):
    cli_env["argv"]("--company_name", "Acme Ltd", "--location", "   ")

    await cli.main()

    state = cli_env["graph"].calls[0]["state"]
    assert state["location"] == "India"
    assert state["company_linkedin"] == ""
    assert state["company_website"] == ""


@pytest.mark.asyncio
async def test_main_ignores_unknown_arguments(cli_env):
    cli_env["argv"]("--company_name", "Acme Ltd", "--not-a-real-flag", "x")

    await cli.main()

    assert cli_env["graph"].calls[0]["state"]["company_name"] == "Acme Ltd"


# ── main(): interactive path ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_main_prompts_interactively_without_company_flag(cli_env, monkeypatch):
    cli_env["argv"]()
    answers = iter([
        "Acme Ltd",
        "https://linkedin.com/company/acme",
        "https://acme.example",
        "Pune",
    ])
    prompts = []

    def fake_input(prompt=""):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)

    await cli.main()

    assert prompts == [
        "Enter Company Name:\n> ",
        "Enter Company LinkedIn URL:\n> ",
        "Enter Company Website URL:\n> ",
        "Enter Company Location (e.g., City, Country):\n> ",
    ]
    state = cli_env["graph"].calls[0]["state"]
    assert state["company_name"] == "Acme Ltd"
    assert state["company_linkedin"] == "https://linkedin.com/company/acme"
    assert state["company_website"] == "https://acme.example"
    assert state["location"] == "Pune"


@pytest.mark.asyncio
async def test_main_stops_when_interactive_company_name_is_empty(cli_env, monkeypatch):
    cli_env["argv"]()
    monkeypatch.setattr("builtins.input", lambda prompt="": "   ")

    await cli.main()

    assert cli_env["graph"].calls == []
    assert FakePipelineLogger.instances == []
    assert cli_env["logger"].events == []
    assert "Company Name cannot be empty. Exiting." in cli_env["out"]()


# ── main(): failures ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_main_reports_graph_errors(cli_env):
    cli_env["argv"]("--company_name", "Acme Ltd")
    cli_env["graph"].error = ValueError("serpapi quota")

    await cli.main()

    types = cli_env["logger"].types()
    assert types == ["pipeline_start", "pipeline_error"]
    error_event = cli_env["logger"].events[-1]["data"]
    assert error_event["company_name"] == "Acme Ltd"
    assert error_event["error"] == "serpapi quota"
    assert "ValueError: serpapi quota" in error_event["traceback"]
    assert "❌ An error occurred during execution: serpapi quota" in cli_env["out"]()


@pytest.mark.asyncio
async def test_main_reports_zero_decision_makers(cli_env):
    cli_env["argv"]("--company_name", "Acme Ltd")

    await cli.main()

    assert "Extracted 0 decision makers for Acme Ltd" in cli_env["out"]()
    assert cli_env["logger"].events[-1]["data"]["decision_makers_count"] == 0
