"""Hermetic unit tests for the Shortlister verification subgraph (verifier.py)."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END

from leadgen.agents.shortlister import verifier
from leadgen.agents.shortlister.verifier import (
    _extract_company_name_from_research_state,
    compress_verifier_research,
    execute_tool_safely,
    verifier_researcher,
    verifier_researcher_tools,
    verifier_supervisor,
    verifier_supervisor_tools,
)
from leadgen.core.telemetry.registry import get_logger, register_logger


class CapturingLogger:
    """Minimal structured logger that records every emitted event."""

    def __init__(self):
        self.events = []

    def event(self, event_type, data, *, level=None, component=None):
        self.events.append({"event_type": event_type, "data": dict(data), "level": level, "component": component})


@pytest.fixture
def capture_events():
    capture = CapturingLogger()
    previous = get_logger()
    register_logger(capture)
    try:
        yield capture
    finally:
        register_logger(previous)


class _FakeTool:
    def __init__(self, name, result=None, error=None):
        self.name = name
        self._result = result
        self._error = error
        self.calls = []

    async def ainvoke(self, args, config):
        self.calls.append(args)
        if self._error is not None:
            raise self._error
        return self._result


class _FakeResearcherSubgraph:
    """Stand-in for the research subgraph so these unit tests never hit the network."""

    async def ainvoke(self, state, config):
        return {
            "compressed_research": "Verified LinkedIn URL: https://www.linkedin.com/company/acme",
            "raw_notes": ["note"],
        }


# ── _extract_company_name_from_research_state ─────────────────────────────────


def test_extract_company_name_from_research_state_present():
    state = {"research_topic": "Company Name: Acme Corp\nOfficial Website: https://acme.com"}

    assert _extract_company_name_from_research_state(state) == "Acme Corp"


def test_extract_company_name_from_research_state_absent():
    assert _extract_company_name_from_research_state({"research_topic": "no name here"}) == ""
    assert _extract_company_name_from_research_state({}) == ""


# ── execute_tool_safely ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_tool_safely_success_returns_tool_result():
    tool = _FakeTool("search", result="TOOL-RESULT")

    result = await execute_tool_safely(tool, {"q": "acme"}, {"configurable": {}}, company_name="Acme")

    assert result == "TOOL-RESULT"
    assert tool.calls == [{"q": "acme"}]


@pytest.mark.asyncio
async def test_execute_tool_safely_non_connection_error_returns_error_string():
    tool = _FakeTool("search", error=ValueError("bad arguments"))

    result = await execute_tool_safely(tool, {}, {"configurable": {}})

    assert result == "Error executing tool: bad arguments"
    assert len(tool.calls) == 1


@pytest.mark.asyncio
async def test_execute_tool_safely_connection_error_reconnects(monkeypatch):
    from leadgen.core.clients import bright_data

    reset_calls = []

    async def fake_reset():
        reset_calls.append(True)

    fresh_tool = _FakeTool("search", result="FRESH-RESULT")
    refresh_kwargs = {}

    async def fake_get_search_only_tools(*args, **kwargs):
        refresh_kwargs.update(kwargs)
        return [fresh_tool]

    monkeypatch.setattr(bright_data, "reset_bright_data_tools", fake_reset)
    monkeypatch.setattr(bright_data, "get_search_only_tools", fake_get_search_only_tools)

    tool = _FakeTool("search", error=ConnectionError("connection reset by peer"))

    result = await execute_tool_safely(tool, {"a": 1}, {"configurable": {}}, company_name="Acme")

    assert result == "FRESH-RESULT"
    assert reset_calls == [True]
    assert refresh_kwargs.get("force_refresh") is True
    assert refresh_kwargs.get("initial_backoff") == 0.1
    assert fresh_tool.calls == [{"a": 1}]


@pytest.mark.asyncio
async def test_execute_tool_safely_exhausted_retries_returns_error(monkeypatch):
    from leadgen.core.clients import bright_data

    async def fake_reset():
        return None

    async def fake_get_search_only_tools(*args, **kwargs):
        return []

    monkeypatch.setattr(bright_data, "reset_bright_data_tools", fake_reset)
    monkeypatch.setattr(bright_data, "get_search_only_tools", fake_get_search_only_tools)

    tool = _FakeTool("search", error=Exception("connection timed out"))

    result = await execute_tool_safely(tool, {}, {"configurable": {}}, max_retries=2)

    assert result == "Error executing tool: connection timed out"
    assert len(tool.calls) == 2


@pytest.mark.asyncio
async def test_execute_tool_safely_tool_without_name_is_handled():
    class _NoNameTool:
        async def ainvoke(self, args, config):
            return "OK"

    result = await execute_tool_safely(_NoNameTool(), {}, {"configurable": {}})

    assert result == "OK"


# ── verifier_researcher ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verifier_researcher_appends_response_and_increments(monkeypatch):
    async def fake_search_tools(*args, **kwargs):
        return []

    monkeypatch.setattr(verifier, "get_search_only_tools", fake_search_tools)

    response = AIMessage(content="researcher response")
    captured = {}

    async def fake_invoke(model_or_factory, input_data, *args, **kwargs):
        captured["messages"] = input_data
        return response

    monkeypatch.setattr(verifier, "invoke_model_with_rate_limit_retry", fake_invoke)

    state = {"researcher_messages": [HumanMessage(content="hi")], "tool_call_iterations": 2}

    cmd = await verifier_researcher(state, {"configurable": {}})

    assert cmd.goto == "verifier_researcher_tools"
    assert cmd.update["researcher_messages"] == [response]
    assert cmd.update["tool_call_iterations"] == 3
    assert captured["messages"][0].type == "system"
    assert captured["messages"][-1].content == "hi"


# ── verifier_researcher_tools ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verifier_researcher_tools_handles_all_tool_call_ids(monkeypatch):
    async def _no_search_tools(*args, **kwargs):
        # Bright Data MCP is not needed to exercise the tool_call_id bookkeeping
        return []

    monkeypatch.setattr(verifier, "get_search_only_tools", _no_search_tools)
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {"name": "think_tool", "args": {"reflection": "evaluating site..."}, "id": "call_think_res_1"},
            {"name": "unknown_tool", "args": {}, "id": "call_unk_res_1"},
        ]
    )

    state = {
        "researcher_messages": [ai_msg],
        "tool_call_iterations": 0,
        "research_topic": "test topic",
        "compressed_research": "",
        "raw_notes": []
    }

    config = {
        "configurable": {
            "max_react_tool_calls": 5
        }
    }

    cmd = await verifier_researcher_tools(state, config)

    researcher_msgs = cmd.update.get("researcher_messages", [])
    returned_ids = {msg.tool_call_id for msg in researcher_msgs if isinstance(msg, ToolMessage)}

    expected_ids = {"call_think_res_1", "call_unk_res_1"}
    assert returned_ids == expected_ids, f"Expected {expected_ids}, got {returned_ids}"


@pytest.mark.asyncio
async def test_verifier_researcher_tools_no_messages_goes_to_compress():
    cmd = await verifier_researcher_tools({"researcher_messages": []}, {"configurable": {}})

    assert cmd.goto == "compress_verifier_research"


@pytest.mark.asyncio
async def test_verifier_researcher_tools_no_tool_calls_goes_to_compress():
    ai_msg = AIMessage(content="no tools requested", tool_calls=[])

    cmd = await verifier_researcher_tools({"researcher_messages": [ai_msg]}, {"configurable": {}})

    assert cmd.goto == "compress_verifier_research"


@pytest.mark.asyncio
async def test_verifier_researcher_tools_exceeded_max_react_goes_to_compress(monkeypatch):
    async def fake_search_tools(*args, **kwargs):
        return []

    monkeypatch.setattr(verifier, "get_search_only_tools", fake_search_tools)
    ai_msg = AIMessage(content="", tool_calls=[{"name": "think_tool", "args": {"reflection": "r"}, "id": "c1"}])
    state = {"researcher_messages": [ai_msg], "tool_call_iterations": 5}

    cmd = await verifier_researcher_tools(state, {"configurable": {"max_react_tool_calls": 5}})

    assert cmd.goto == "compress_verifier_research"
    msgs = cmd.update["researcher_messages"]
    assert isinstance(msgs[0], ToolMessage)
    assert msgs[0].tool_call_id == "c1"
    assert msgs[0].content == "Reflection recorded: r"


@pytest.mark.asyncio
async def test_verifier_researcher_tools_research_complete_goes_to_compress(monkeypatch):
    async def fake_search_tools(*args, **kwargs):
        return []

    monkeypatch.setattr(verifier, "get_search_only_tools", fake_search_tools)
    ai_msg = AIMessage(content="", tool_calls=[{"name": "ResearchComplete", "args": {}, "id": "rc1"}])
    state = {"researcher_messages": [ai_msg], "tool_call_iterations": 0}

    cmd = await verifier_researcher_tools(state, {"configurable": {"max_react_tool_calls": 10}})

    assert cmd.goto == "compress_verifier_research"
    msgs = cmd.update["researcher_messages"]
    assert msgs[0].content == "Research complete."
    assert msgs[0].tool_call_id == "rc1"


@pytest.mark.asyncio
async def test_verifier_researcher_tools_unknown_tool_placeholder_content(monkeypatch):
    async def fake_search_tools(*args, **kwargs):
        return []

    monkeypatch.setattr(verifier, "get_search_only_tools", fake_search_tools)
    ai_msg = AIMessage(content="", tool_calls=[{"name": "mystery_tool", "args": {}, "id": "u1"}])
    state = {"researcher_messages": [ai_msg], "tool_call_iterations": 0}

    cmd = await verifier_researcher_tools(state, {"configurable": {"max_react_tool_calls": 10}})

    assert cmd.goto == "verifier_researcher"
    msgs = cmd.update["researcher_messages"]
    assert msgs[0].content == "Executed tool mystery_tool"
    assert msgs[0].name == "mystery_tool"
    assert msgs[0].tool_call_id == "u1"


# ── compress_verifier_research ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compress_verifier_research_returns_compressed_and_raw_notes(monkeypatch):
    class _Response:
        content = "COMPRESSED"

    async def fake_invoke(model_or_factory, messages, *args, **kwargs):
        return _Response()

    monkeypatch.setattr(verifier, "invoke_model_with_rate_limit_retry", fake_invoke)

    state = {
        "researcher_messages": [
            AIMessage(content="ai note"),
            ToolMessage(content="tool note", tool_call_id="1"),
        ],
    }

    result = await compress_verifier_research(state, {"configurable": {}})

    assert result["compressed_research"] == "COMPRESSED"
    assert result["raw_notes"] == ["ai note\ntool note"]


@pytest.mark.asyncio
async def test_compress_verifier_research_model_error_returns_error_string(monkeypatch):
    async def fake_invoke(model_or_factory, messages, *args, **kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(verifier, "invoke_model_with_rate_limit_retry", fake_invoke)

    state = {"researcher_messages": [AIMessage(content="ai note")]}

    result = await compress_verifier_research(state, {"configurable": {}})

    assert result["compressed_research"] == "Error synthesizing research: llm down"
    assert result["raw_notes"] == []


# ── verifier_supervisor ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verifier_supervisor_appends_response_and_increments(monkeypatch):
    response = AIMessage(
        content="supervisor",
        tool_calls=[{"name": "ResearchComplete", "args": {}, "id": "c1"}],
    )

    async def fake_invoke(model_or_factory, messages, *args, **kwargs):
        return response

    monkeypatch.setattr(verifier, "invoke_model_with_rate_limit_retry", fake_invoke)

    state = {"supervisor_messages": [HumanMessage(content="go")], "research_iterations": 4}

    cmd = await verifier_supervisor(state, {"configurable": {}})

    assert cmd.goto == "verifier_supervisor_tools"
    assert cmd.update["supervisor_messages"] == [response]
    assert cmd.update["research_iterations"] == 5


@pytest.mark.asyncio
async def test_verifier_supervisor_reraises_after_emitting_pipeline_error(monkeypatch, capture_events):
    async def fake_invoke(model_or_factory, messages, *args, **kwargs):
        raise RuntimeError("supervisor boom")

    monkeypatch.setattr(verifier, "invoke_model_with_rate_limit_retry", fake_invoke)

    with pytest.raises(RuntimeError, match="supervisor boom"):
        await verifier_supervisor({"supervisor_messages": []}, {"configurable": {}})

    errors = [event for event in capture_events.events if event["event_type"] == "pipeline_error"]
    assert len(errors) == 1
    assert errors[0]["data"]["node"] == "verifier_supervisor"
    assert errors[0]["data"]["error"] == "supervisor boom"


# ── verifier_supervisor_tools ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verifier_supervisor_tools_handles_all_tool_call_ids(monkeypatch):
    monkeypatch.setattr(verifier, "researcher_subgraph", _FakeResearcherSubgraph())
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {"name": "think_tool", "args": {"reflection": "thinking..."}, "id": "call_OuKup888RdNyetddwJ4gWvMk"},
            {
                "name": "ConductResearch",
                "args": {
                    "company_name": "TCS",
                    "website": "https://tcs.com",
                    "description": "IT services",
                    "research_topic": "verify TCS",
                },
                "id": "call_conduct_1",
            },
            {"name": "ResearchComplete", "args": {}, "id": "call_complete_1"},
        ]
    )

    state = {
        "supervisor_messages": [ai_msg],
        "research_iterations": 0,
        "research_brief": "test brief"
    }

    config = {
        "configurable": {
            "max_verifier_iterations": 3,
            "max_concurrent_research_units": 1
        }
    }

    cmd = await verifier_supervisor_tools(state, config)

    supervisor_msgs = cmd.update.get("supervisor_messages", [])
    returned_ids = {msg.tool_call_id for msg in supervisor_msgs if isinstance(msg, ToolMessage)}

    expected_ids = {"call_OuKup888RdNyetddwJ4gWvMk", "call_conduct_1", "call_complete_1"}
    assert returned_ids == expected_ids, f"Expected {expected_ids}, got {returned_ids}"


@pytest.mark.asyncio
async def test_verifier_supervisor_tools_warns_when_no_tool_calls_and_no_research():
    ai_msg = AIMessage(content="we should think", tool_calls=[])

    cmd = await verifier_supervisor_tools({"supervisor_messages": [ai_msg], "research_iterations": 0}, {"configurable": {}})

    assert cmd.goto == "verifier_supervisor"
    msgs = cmd.update["supervisor_messages"]
    assert len(msgs) == 1
    assert isinstance(msgs[0], HumanMessage)
    assert "ConductResearch" in msgs[0].content


@pytest.mark.asyncio
async def test_verifier_supervisor_tools_defers_beyond_concurrency_limit(monkeypatch):
    monkeypatch.setattr(verifier, "researcher_subgraph", _FakeResearcherSubgraph())
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "ConductResearch",
                "args": {"company_name": "A", "website": "a.com", "description": "d", "research_topic": "t"},
                "id": "c1",
            },
            {
                "name": "ConductResearch",
                "args": {"company_name": "B", "website": "b.com", "description": "d", "research_topic": "t"},
                "id": "c2",
            },
        ],
    )
    state = {"supervisor_messages": [ai_msg], "research_iterations": 0}

    cmd = await verifier_supervisor_tools(
        state, {"configurable": {"max_concurrent_research_units": 1, "max_verifier_iterations": 15}}
    )

    assert cmd.goto == "verifier_supervisor"
    by_id = {msg.tool_call_id: msg for msg in cmd.update["supervisor_messages"] if isinstance(msg, ToolMessage)}
    assert by_id["c1"].content.startswith("Verified LinkedIn URL:")
    assert by_id["c2"].content == "[Notice: Concurrency limit reached for this round. Task deferred.]"


@pytest.mark.asyncio
async def test_verifier_supervisor_tools_research_complete_ends_and_collects_notes(monkeypatch):
    class _FakeResearcher:
        async def ainvoke(self, state, config):
            return {"compressed_research": "FINDINGS", "raw_notes": ["note-one", "note-two"]}

    monkeypatch.setattr(verifier, "researcher_subgraph", _FakeResearcher())
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "ConductResearch",
                "args": {"company_name": "Acme", "website": "acme.com", "description": "d", "research_topic": "t"},
                "id": "cr1",
            },
            {"name": "ResearchComplete", "args": {}, "id": "rc1"},
        ],
    )
    state = {"supervisor_messages": [ai_msg], "research_iterations": 1, "research_brief": "brief"}

    cmd = await verifier_supervisor_tools(state, {"configurable": {}})

    assert cmd.goto == END
    assert cmd.update["notes"] == ["FINDINGS"]
    assert cmd.update["raw_notes"] == ["note-one\nnote-two"]
    assert cmd.update["research_brief"] == "brief"
    by_id = {msg.tool_call_id: msg for msg in cmd.update["supervisor_messages"] if isinstance(msg, ToolMessage)}
    assert by_id["cr1"].content == "FINDINGS"
    assert by_id["rc1"].content == "Research marked complete."


@pytest.mark.asyncio
async def test_verifier_supervisor_tools_think_tool_branch():
    ai_msg = AIMessage(content="", tool_calls=[{"name": "think_tool", "args": {"reflection": "plan A"}, "id": "tt1"}])
    state = {"supervisor_messages": [ai_msg], "research_iterations": 0}

    cmd = await verifier_supervisor_tools(state, {"configurable": {}})

    assert cmd.goto == "verifier_supervisor"
    msgs = [msg for msg in cmd.update["supervisor_messages"] if isinstance(msg, ToolMessage)]
    assert msgs[0].content == "Reflection recorded: plan A"
    assert msgs[0].tool_call_id == "tt1"


@pytest.mark.asyncio
async def test_verifier_supervisor_tools_exceeded_iterations_ends():
    ai_msg = AIMessage(content="", tool_calls=[{"name": "think_tool", "args": {"reflection": "x"}, "id": "t1"}])
    state = {"supervisor_messages": [ai_msg], "research_iterations": 6}

    cmd = await verifier_supervisor_tools(state, {"configurable": {"max_verifier_iterations": 5}})

    assert cmd.goto == END


@pytest.mark.asyncio
async def test_verifier_supervisor_tools_unknown_tool_content(monkeypatch):
    ai_msg = AIMessage(content="", tool_calls=[{"name": "weird_tool", "args": {}, "id": "w1"}])
    state = {"supervisor_messages": [ai_msg], "research_iterations": 0}

    cmd = await verifier_supervisor_tools(state, {"configurable": {}})

    assert cmd.goto == "verifier_supervisor"
    by_id = {msg.tool_call_id: msg for msg in cmd.update["supervisor_messages"] if isinstance(msg, ToolMessage)}
    assert by_id["w1"].content == "Executed tool weird_tool"
    assert by_id["w1"].name == "weird_tool"
