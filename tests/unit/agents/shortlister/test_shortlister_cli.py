"""Unit tests for the Shortlister CLI entry point (``leadgen.agents.shortlister.cli``)."""

import asyncio
import sys
from datetime import datetime

import pytest
from langchain_core.messages import HumanMessage

from leadgen import config
from leadgen.agents.shortlister import cli


class CapturingLogger:
    """Stand-in for the StructuredLoggerAdapter returned by _bootstrap_logger."""

    def __init__(self):
        self.events = []

    def event(self, event_type, data, **kwargs):
        self.events.append({"event_type": event_type, "data": dict(data), **kwargs})

    def types(self):
        return [event["event_type"] for event in self.events]


class FakePipelineLogger:
    """Records the session id and answers the token/cost summary call."""

    instances = []

    def __init__(self, session_id):
        self.session_id = session_id
        self.log_store = type("Store", (), {"log_file": f"/tmp/run_{session_id}.jsonl"})()
        FakePipelineLogger.instances.append(self)

    def get_token_usage_summary(self):
        return {
            "total_prompt_tokens": 100,
            "total_completion_tokens": 20,
            "total_tokens": 120,
            "cost_input": 0.000025,
            "cost_output": 0.00004,
            "total_cost": 0.000065,
        }


class FakeGraph:
    def __init__(self, result=None, error=None, recorder=None):
        self.result = result if result is not None else {"verified_companies": []}
        self.error = error
        self.recorder = recorder

    async def ainvoke(self, state, config=None):
        if self.recorder is not None:
            self.recorder["state"] = state
            self.recorder["config"] = config
        if self.error is not None:
            raise self.error
        return self.result


class FakeAsyncSqliteSaver:
    """Replaces the real checkpointer: records the DB path and yields a fake saver."""

    paths = []

    @classmethod
    def from_conn_string(cls, path):
        cls.paths.append(path)

        class _Ctx:
            async def __aenter__(self):
                return "sqlite-saver"

            async def __aexit__(self, *exc_info):
                return False

        return _Ctx()


@pytest.fixture
def cli_env(monkeypatch, isolated_var, capsys):
    """Wire the CLI's collaborators to fakes; return the collected handles."""
    FakePipelineLogger.instances.clear()
    FakeAsyncSqliteSaver.paths.clear()

    logger = CapturingLogger()
    recorder: dict = {}
    graph = FakeGraph(recorder=recorder)

    monkeypatch.setattr(cli, "_bootstrap_logger", lambda session_id: logger)
    monkeypatch.setattr(cli, "PipelineLogger", FakePipelineLogger)
    monkeypatch.setattr(cli, "build_graph", lambda checkpointer=None: graph)
    monkeypatch.setattr("langgraph.checkpoint.sqlite.aio.AsyncSqliteSaver", FakeAsyncSqliteSaver)

    return {
        "logger": logger,
        "graph": graph,
        "recorder": recorder,
        "out": lambda: capsys.readouterr().out,
        "argv": lambda *args: monkeypatch.setattr(sys, "argv", ["leadgen.agents.shortlister", *args]),
        "env": monkeypatch,
    }


# ── _bootstrap_logger ──────────────────────────────────────────────────────────

def test_bootstrap_logger_binds_agent_and_registers(monkeypatch, isolated_var):
    seen = {}

    def fake_setup_logging(agent, run_id):
        seen["agent"] = agent
        seen["run_id"] = run_id
        return "logger-sentinel"

    registered = []
    monkeypatch.setattr(cli, "setup_logging", fake_setup_logging)
    monkeypatch.setattr(cli, "set_logger", registered.append)

    result = cli._bootstrap_logger("session-xyz")

    assert result == "logger-sentinel"
    assert seen == {"agent": "shortlister", "run_id": "session-xyz"}
    assert registered == ["logger-sentinel"]


# ── run() ──────────────────────────────────────────────────────────────────────

def test_run_prepares_dirs_and_runs_main(monkeypatch, isolated_var):
    calls = []
    monkeypatch.setattr(config, "ensure_runtime_dirs", lambda: calls.append("dirs"))

    async def fake_main():
        calls.append("main")

    monkeypatch.setattr(cli, "main", fake_main)

    def fake_asyncio_run(coro):
        coro.close()  # never awaited on purpose — keep the warning out of the log
        calls.append("asyncio.run")

    monkeypatch.setattr(asyncio, "run", fake_asyncio_run)

    cli.run()
    assert calls == ["dirs", "asyncio.run"]


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
    monkeypatch.setattr(cli.sys, "platform", "linux")
    cli.run()
    assert applied == []


# ── main(): happy path ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_main_runs_graph_with_query_and_reports_summary(cli_env, monkeypatch):
    monkeypatch.setenv("PIPELINE_RUN_ID", "run-42")
    cli_env["argv"]("Indian specialty chemicals above 500 Cr")

    result = {
        "verified_companies": [
            {"name": "Acme Chem", "ticker": "ACME", "revenue_ttm": 5_000_000_000.0,
             "website": "https://acme.example", "linkedin_verified": "https://linkedin.com/company/acme",
             "linkedin_confirmed": True},
            # a company with no revenue hit renders "N/A" instead of a formatted number
            {"name": "Beta Ltd", "ticker": "BETA", "revenue_ttm": 0,
             "website": "NOT FOUND", "linkedin_verified": "NOT FOUND",
             "linkedin_confirmed": False},
        ]
    }
    cli_env["graph"].result = result

    await cli.main()

    # session id comes from the injected env var, and the graph got the query
    assert FakePipelineLogger.instances[0].session_id == "run-42"
    sent = cli_env["recorder"]["state"]
    assert sent == {"messages": [HumanMessage(content="Indian specialty chemicals above 500 Cr")]}

    runnable_config = cli_env["recorder"]["config"]
    assert runnable_config["configurable"] == {
        "thread_id": "run-42",
        "screener_market": config.SCREENER_MARKET,
        "screener_limit": config.SCREENER_LIMIT,
        "top_n_companies": config.TOP_N_COMPANIES,
    }
    assert runnable_config["callbacks"] == [FakePipelineLogger.instances[0]]

    # the checkpointer is opened on the isolated shortlister DB
    assert FakeAsyncSqliteSaver.paths == [config.MEMORY_DB_PATH]

    assert cli_env["logger"].types() == ["pipeline_start", "pipeline_end"]
    start = cli_env["logger"].events[0]
    assert start["data"]["user_query"] == "Indian specialty chemicals above 500 Cr"
    assert start["component"] == "main"
    end = cli_env["logger"].events[1]
    assert end["data"]["company_count"] == 2
    assert end["data"]["total_tokens"] == 120

    out = cli_env["out"]()
    assert "SHORTLISTER AGENT PIPELINE" in out
    assert "FINAL SHORTLIST SUMMARY (2 Companies)" in out
    assert "Acme Chem" in out and "Confirmed ✅" in out
    assert "Unverified ⚠️" in out
    assert "Rev: N/A" in out
    assert "Total API Cost:     $0.000065" in out


@pytest.mark.asyncio
async def test_main_generates_session_id_when_env_absent(cli_env, monkeypatch):
    monkeypatch.delenv("PIPELINE_RUN_ID", raising=False)
    cli_env["argv"]("anything")

    await cli.main()

    session_id = FakePipelineLogger.instances[0].session_id
    assert session_id.startswith("session-")
    # session-YYYYmmdd-HHMMSS
    datetime.strptime(session_id, "session-%Y%m%d-%H%M%S")


# ── main(): interactive + guard rails ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_main_prompts_for_query_when_no_arguments(cli_env, monkeypatch):
    monkeypatch.delenv("PIPELINE_RUN_ID", raising=False)
    cli_env["argv"]()  # no positional query

    prompts = []

    def fake_input(prompt=""):
        prompts.append(prompt)
        return "  Pharma companies in Pune  "

    monkeypatch.setattr("builtins.input", fake_input)

    await cli.main()

    assert prompts == ["Describe the company profile you are looking for:\n> "]
    # whitespace is preserved by the CLI (the graph receives the raw string)
    assert cli_env["recorder"]["state"]["messages"][0].content == "  Pharma companies in Pune  "


@pytest.mark.asyncio
async def test_main_exits_early_on_empty_input(cli_env, monkeypatch):
    cli_env["argv"]("   ")

    await cli.main()

    assert cli_env["logger"].types() == ["pipeline_error"]
    assert cli_env["logger"].events[0]["data"] == {"error": "Empty input. Exiting."}
    assert "❌ Empty input. Exiting." in cli_env["out"]()
    assert cli_env["recorder"] == {}          # the graph was never invoked
    assert FakePipelineLogger.instances == []


@pytest.mark.asyncio
async def test_main_reports_graph_errors(cli_env, monkeypatch):
    cli_env["argv"]("anything")
    cli_env["graph"].error = RuntimeError("screener exploded")

    await cli.main()

    types = cli_env["logger"].types()
    assert types == ["pipeline_start", "pipeline_error"]
    error_event = cli_env["logger"].events[-1]["data"]
    assert error_event["error"] == "screener exploded"
    assert "RuntimeError: screener exploded" in error_event["traceback"]
    assert "❌ An error occurred during execution: screener exploded" in cli_env["out"]()


@pytest.mark.asyncio
async def test_main_joins_multiple_positional_arguments(cli_env):
    cli_env["argv"]("Indian", "specialty", "chemicals")

    await cli.main()

    assert cli_env["recorder"]["state"]["messages"][0].content == "Indian specialty chemicals"


@pytest.mark.asyncio
async def test_main_reports_zero_companies(cli_env):
    cli_env["argv"]("nothing matches")
    cli_env["graph"].result = {"verified_companies": []}

    await cli.main()

    out = cli_env["out"]()
    assert "FINAL SHORTLIST SUMMARY (0 Companies)" in out
    assert cli_env["logger"].events[-1]["data"]["company_count"] == 0


@pytest.mark.asyncio
async def test_main_handles_missing_verified_companies_key(cli_env):
    cli_env["argv"]("query")
    cli_env["graph"].result = {}

    await cli.main()

    assert "FINAL SHORTLIST SUMMARY (0 Companies)" in cli_env["out"]()
    assert cli_env["logger"].types() == ["pipeline_start", "pipeline_end"]


@pytest.mark.asyncio
async def test_summary_print_breaks_on_incomplete_company_records(cli_env):
    """Documents current fragility: the summary line formats ticker/website/LinkedIn
    with ``:<width``, so a company record whose values are ``None`` (rather than
    missing-but-populated strings) raises TypeError *after* the pipeline succeeded."""
    cli_env["argv"]("query")
    cli_env["graph"].result = {"verified_companies": [{"name": "No Fields Ltd"}]}

    await cli.main()

    # pipeline_end is emitted before the summary is printed, so the crash adds a
    # pipeline_error *after* it (the run itself already succeeded and saved its files)
    assert cli_env["logger"].types() == ["pipeline_start", "pipeline_end", "pipeline_error"]
    error = cli_env["logger"].events[-1]["data"]
    assert "unsupported format string passed to NoneType.__format__" in error["error"]
