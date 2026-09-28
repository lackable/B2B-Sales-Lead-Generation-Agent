"""Unit tests for :mod:`leadgen.core.llm`."""

from datetime import datetime

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from leadgen.core import llm
from leadgen.core.llm import (
    MAX_MESSAGE_CONTENT_CHARS,
    MAX_TOOL_OUTPUT_CHARS,
    DeploymentManager,
    get_chat_model,
    get_model_token_limit,
    get_today_str,
    invoke_model_with_rate_limit_retry,
    is_token_limit_exceeded,
    remove_up_to_last_ai_message,
    sanitize_input_messages,
    think_tool,
    truncate_tool_output,
)


# ── DeploymentManager ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deployment_manager_empty_returns_blank(monkeypatch):
    monkeypatch.setattr(llm.config, "OPENAI_MODELS", [])
    manager = DeploymentManager([])

    assert manager.deployments == []
    assert manager.get_current_deployment() == ""
    assert await manager.switch_deployment() == ("", True, "")


@pytest.mark.asyncio
async def test_deployment_manager_rotation_and_full_cycle():
    manager = DeploymentManager(["a", "b", "c"])
    assert manager.get_current_deployment() == "a"

    new_dep, is_full_cycle, prev_dep = await manager.switch_deployment()
    assert (new_dep, is_full_cycle, prev_dep) == ("b", False, "a")
    assert manager.get_current_deployment() == "b"

    assert await manager.switch_deployment() == ("c", False, "b")
    # Wrapping back to index 0 is the only "full cycle"
    assert await manager.switch_deployment() == ("a", True, "c")
    assert await manager.switch_deployment() == ("b", False, "a")


# ── get_chat_model ────────────────────────────────────────────────────────────

def test_get_chat_model_raises_without_base_url(monkeypatch):
    monkeypatch.setattr(llm.config, "OPENAI_BASE_URL", None)
    monkeypatch.setattr(llm.config, "OPENAI_API_KEY", "key")
    with pytest.raises(RuntimeError, match="LLM not configured"):
        get_chat_model("model-a")


def test_get_chat_model_raises_without_api_key(monkeypatch):
    monkeypatch.setattr(llm.config, "OPENAI_BASE_URL", "http://endpoint/v1")
    monkeypatch.setattr(llm.config, "OPENAI_API_KEY", None)
    with pytest.raises(RuntimeError, match="LLM not configured"):
        get_chat_model("model-a")


def test_get_chat_model_raises_without_model(monkeypatch):
    monkeypatch.setattr(llm.config, "OPENAI_BASE_URL", "http://endpoint/v1")
    monkeypatch.setattr(llm.config, "OPENAI_API_KEY", "key")
    monkeypatch.setattr(llm.config, "OPENAI_MODELS", [])
    monkeypatch.setattr(llm, "deployment_manager", DeploymentManager([]))
    with pytest.raises(RuntimeError, match="LLM not configured"):
        get_chat_model()


def test_get_chat_model_passes_expected_kwargs(monkeypatch):
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(llm.config, "OPENAI_BASE_URL", "http://endpoint/v1")
    monkeypatch.setattr(llm.config, "OPENAI_API_KEY", "secret")

    model = get_chat_model("gpt-x", max_retries=7, timeout=12.5)

    assert isinstance(model, FakeChatOpenAI)
    assert captured == {
        "model": "gpt-x",
        "api_key": "secret",
        "base_url": "http://endpoint/v1",
        "temperature": 0.0,
        "max_retries": 7,
        "request_timeout": 12.5,
        "timeout": 12.5,
    }


def test_get_chat_model_default_retry_and_timeout(monkeypatch):
    captured = {}

    def fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return "model-instance"

    monkeypatch.setattr(llm, "ChatOpenAI", fake_chat_openai)
    monkeypatch.setattr(llm.config, "OPENAI_BASE_URL", "http://endpoint/v1")
    monkeypatch.setattr(llm.config, "OPENAI_API_KEY", "secret")

    assert get_chat_model("m") == "model-instance"
    assert captured["max_retries"] == 3
    assert captured["request_timeout"] == 90.0
    assert captured["timeout"] == 90.0


def test_get_chat_model_uses_current_deployment_when_name_omitted(monkeypatch):
    captured = {}

    def fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return "model-instance"

    monkeypatch.setattr(llm, "ChatOpenAI", fake_chat_openai)
    monkeypatch.setattr(llm.config, "OPENAI_BASE_URL", "http://endpoint/v1")
    monkeypatch.setattr(llm.config, "OPENAI_API_KEY", "secret")
    monkeypatch.setattr(llm, "deployment_manager", DeploymentManager(["dep-1", "dep-2"]))

    get_chat_model()
    assert captured["model"] == "dep-1"


# ── truncate_tool_output ──────────────────────────────────────────────────────

def test_truncate_tool_output_short_and_default_limit():
    assert truncate_tool_output("hello") == "hello"
    assert MAX_TOOL_OUTPUT_CHARS == 40_000


def test_truncate_tool_output_none_is_empty_string():
    assert truncate_tool_output(None) == ""


def test_truncate_tool_output_exact_limit_unchanged():
    value = "x" * 10
    assert truncate_tool_output(value, max_chars=10) == value


def test_truncate_tool_output_over_limit_appends_notice():
    result = truncate_tool_output("abcdefghij", max_chars=5)
    assert result == (
        "abcde\n\n[Warning: Tool output truncated from 10 to 5 characters to fit API payload limits.]"
    )


def test_truncate_tool_output_stringifies_non_strings():
    assert truncate_tool_output(123) == "123"


# ── sanitize_input_messages ───────────────────────────────────────────────────

def test_sanitize_input_messages_truncates_over_long_list_content():
    long_content = "a" * (MAX_MESSAGE_CONTENT_CHARS + 10)
    original = HumanMessage(content=long_content)

    result = sanitize_input_messages([original])

    expected = "a" * MAX_MESSAGE_CONTENT_CHARS + (
        f"\n\n[Warning: Message content truncated from {len(long_content)} "
        f"to {MAX_MESSAGE_CONTENT_CHARS} characters to satisfy API limits.]"
    )
    assert len(result) == 1
    assert result[0].content == expected
    assert result[0] is not original
    assert original.content == long_content  # original untouched


def test_sanitize_input_messages_passthrough_for_short_list():
    messages = [HumanMessage(content="hi"), AIMessage(content="yo")]
    result = sanitize_input_messages(messages)
    assert result == messages
    assert result[0] is messages[0]
    assert result[1] is messages[1]


def test_sanitize_input_messages_appends_non_message_entries():
    message = HumanMessage(content="ok")
    result = sanitize_input_messages([message, 42])
    assert result[0] is message
    assert result[1] == 42


def test_sanitize_input_messages_single_short_message_unchanged():
    message = HumanMessage(content="short")
    assert sanitize_input_messages(message) is message


def test_sanitize_input_messages_single_long_message_truncated():
    long_content = "b" * (MAX_MESSAGE_CONTENT_CHARS + 5)
    message = HumanMessage(content=long_content)
    result = sanitize_input_messages(message)
    assert result is not message
    assert result.content == "b" * MAX_MESSAGE_CONTENT_CHARS + (
        f"\n\n[Warning: Message content truncated from {len(long_content)} "
        f"to {MAX_MESSAGE_CONTENT_CHARS} characters to satisfy API limits.]"
    )


def test_sanitize_input_messages_non_message_passthrough():
    assert sanitize_input_messages("plain string") == "plain string"
    assert sanitize_input_messages({"role": "user"}) == {"role": "user"}


def test_sanitize_input_messages_honours_custom_limit():
    result = sanitize_input_messages([HumanMessage(content="1234567890")], max_chars=4)
    assert result[0].content == (
        "1234\n\n[Warning: Message content truncated from 10 to 4 characters to satisfy API limits.]"
    )


# ── invoke_model_with_rate_limit_retry ────────────────────────────────────────

class _FakeModel:
    """A model whose ``ainvoke`` fails a configurable number of times."""

    def __init__(self, deployment, state):
        self.deployment = deployment
        self.state = state

    async def ainvoke(self, _data):
        self.state["calls"] += 1
        if self.state["calls"] <= self.state["fail_times"]:
            raise Exception(self.state["error"])
        return f"ok:{self.deployment}"


def _factory(state, record):
    def factory(deployment):
        record.append(deployment)
        return _FakeModel(deployment, state)
    return factory


def _record_sleeps(monkeypatch, module):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(module.asyncio, "sleep", fake_sleep)
    return sleeps


@pytest.mark.asyncio
async def test_invoke_succeeds_on_first_attempt(monkeypatch):
    monkeypatch.setattr(llm, "deployment_manager", DeploymentManager(["a"]))
    state = {"calls": 0, "fail_times": 0, "error": "boom"}
    record = []

    result = await invoke_model_with_rate_limit_retry(_factory(state, record), "prompt")

    assert result == "ok:a"
    assert record == ["a"]


@pytest.mark.asyncio
async def test_invoke_rate_limit_rotates_to_next_deployment(monkeypatch):
    monkeypatch.setattr(llm, "deployment_manager", DeploymentManager(["a", "b"]))
    state = {"calls": 0, "fail_times": 1, "error": "429 rate limit hit"}
    record = []

    result = await invoke_model_with_rate_limit_retry(_factory(state, record), "prompt")

    assert result == "ok:b"
    # Factory was re-invoked with the switched-to deployment name
    assert record == ["a", "b"]


@pytest.mark.asyncio
async def test_invoke_full_cycle_sleeps_with_config_default(monkeypatch):
    monkeypatch.setattr(llm, "deployment_manager", DeploymentManager(["only"]))
    monkeypatch.setattr(llm.config, "RATE_LIMIT_CYCLE_WAIT_SECONDS", 7)
    sleeps = _record_sleeps(monkeypatch, llm)
    state = {"calls": 0, "fail_times": 99, "error": "429"}
    record = []

    with pytest.raises(Exception, match="429"):
        await invoke_model_with_rate_limit_retry(_factory(state, record), "prompt", max_retries=2)

    # attempts 0 and 1 wrap the full cycle and sleep; attempt 2 raises
    assert sleeps == [7, 7]
    assert record == ["only", "only", "only"]


@pytest.mark.asyncio
async def test_invoke_sleep_seconds_argument_overrides_config(monkeypatch):
    monkeypatch.setattr(llm, "deployment_manager", DeploymentManager(["only"]))
    monkeypatch.setattr(llm.config, "RATE_LIMIT_CYCLE_WAIT_SECONDS", 7)
    sleeps = _record_sleeps(monkeypatch, llm)
    state = {"calls": 0, "fail_times": 99, "error": "429"}
    record = []

    with pytest.raises(Exception, match="429"):
        await invoke_model_with_rate_limit_retry(
            _factory(state, record), "prompt", max_retries=1, sleep_seconds=99
        )

    assert sleeps == [99]


@pytest.mark.asyncio
async def test_invoke_non_retryable_error_raises_immediately(monkeypatch):
    monkeypatch.setattr(llm, "deployment_manager", DeploymentManager(["a", "b"]))
    sleeps = _record_sleeps(monkeypatch, llm)
    state = {"calls": 0, "fail_times": 99, "error": "some value error"}
    record = []

    with pytest.raises(Exception, match="some value error"):
        await invoke_model_with_rate_limit_retry(_factory(state, record), "prompt")

    assert record == ["a"]  # never rotated
    assert sleeps == []  # never slept


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    ["429", "rate_limit", "too_many_requests", "timeout", "Request timed out", "connection reset", "ReadTimeout"],
)
async def test_invoke_retryable_error_strings_rotate(monkeypatch, error):
    monkeypatch.setattr(llm, "deployment_manager", DeploymentManager(["a", "b"]))
    monkeypatch.setattr(llm.config, "RATE_LIMIT_CYCLE_WAIT_SECONDS", 0)
    _record_sleeps(monkeypatch, llm)
    state = {"calls": 0, "fail_times": 1, "error": error}
    record = []

    result = await invoke_model_with_rate_limit_retry(_factory(state, record), "prompt")

    assert result == "ok:b"
    assert record == ["a", "b"]


@pytest.mark.asyncio
async def test_invoke_accepts_a_model_instance_directly(monkeypatch):
    monkeypatch.setattr(llm, "deployment_manager", DeploymentManager(["a"]))

    class _DirectModel:
        async def ainvoke(self, _data):
            return "direct-ok"

    result = await invoke_model_with_rate_limit_retry(_DirectModel(), "prompt")
    assert result == "direct-ok"


# ── Small helpers ─────────────────────────────────────────────────────────────

def test_get_today_str_format():
    today = get_today_str()
    assert len(today) == 10
    assert today == datetime.now().strftime("%Y-%m-%d")


def test_remove_up_to_last_ai_message_keeps_seed_and_last_ai():
    seed = HumanMessage(content="seed")
    first_ai = AIMessage(content="first ai")
    human = HumanMessage(content="human")
    last_ai = AIMessage(content="last ai")
    messages = [seed, first_ai, human, last_ai]

    result = remove_up_to_last_ai_message(messages)

    assert result == [seed, last_ai]
    assert result[0] is seed
    assert result[1] is last_ai


def test_remove_up_to_last_ai_message_without_ai_is_unchanged():
    messages = [HumanMessage(content="a"), HumanMessage(content="b")]
    assert remove_up_to_last_ai_message(messages) == messages


def test_remove_up_to_last_ai_message_only_ai_at_index_zero_is_unchanged():
    messages = [AIMessage(content="only"), HumanMessage(content="h")]
    assert remove_up_to_last_ai_message(messages) == messages


def test_remove_up_to_last_ai_message_ai_at_index_one_keeps_tail():
    seed = HumanMessage(content="seed")
    ai = AIMessage(content="ai")
    tail = HumanMessage(content="tail")
    messages = [seed, ai, tail]
    # Only messages *before* the last AI message are dropped, so the seed plus
    # everything from that AI message onwards is retained.
    result = remove_up_to_last_ai_message(messages)
    assert result == [seed, ai, tail]
    assert result[0] is seed


def test_is_token_limit_exceeded():
    assert is_token_limit_exceeded(Exception("maximum token limit reached"), "m") is True
    assert is_token_limit_exceeded(Exception("Context Length exceeded"), "m") is True
    assert is_token_limit_exceeded(Exception("unrelated failure"), "m") is False


@pytest.mark.parametrize(
    "model_name,expected",
    [
        (None, 8192),
        ("", 8192),
        ("gpt-5-mini-2", 128000),
        ("gpt-5.4-mini", 128000),
        ("gpt-4o", 128000),
        ("gpt-4o-mini", 128000),
        ("gpt-3.5-turbo", 8192),
        ("claude-3-sonnet", 8192),
    ],
)
def test_get_model_token_limit(model_name, expected):
    assert get_model_token_limit(model_name) == expected


def test_think_tool_returns_reflection_string():
    assert think_tool.invoke({"reflection": "plan the search"}) == "Reflection recorded: plan the search"
    assert think_tool.name == "think_tool"
