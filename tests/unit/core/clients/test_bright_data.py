"""Unit tests for :mod:`leadgen.core.clients.bright_data`."""

import asyncio

import pytest

from leadgen.core.clients import bright_data


class _FakeTool:
    def __init__(self, name):
        self.name = name


class _ClientState:
    """Shared state across the per-attempt fake client instances."""

    def __init__(self, tools, fail_times=0, error="boom"):
        self.tools = tools
        self.fail_times = fail_times
        self.error = error
        self.get_tools_calls = 0
        self.constructed = []
        self.aclose_calls = 0


def _make_fake_client_cls(state):
    class FakeClient:
        def __init__(self, config):
            state.constructed.append(config)

        async def get_tools(self):
            state.get_tools_calls += 1
            if state.get_tools_calls <= state.fail_times:
                raise RuntimeError(state.error)
            return list(state.tools)

        async def aclose(self):
            state.aclose_calls += 1

    return FakeClient


def _record_sleeps(monkeypatch):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(bright_data.asyncio, "sleep", fake_sleep)
    return sleeps


@pytest.fixture
def bd(monkeypatch):
    """Reset the module-level client/tools/lock globals around each test."""
    monkeypatch.setattr(bright_data, "_mcp_client", None)
    monkeypatch.setattr(bright_data, "_cached_tools", None)
    monkeypatch.setattr(bright_data, "_mcp_lock", asyncio.Lock())
    return bright_data


def _configure(monkeypatch, url="https://mcp.example/sse", api_key=None):
    monkeypatch.setattr(bright_data.config, "BRIGHT_DATA_MCP_URL", url)
    monkeypatch.setattr(bright_data.config, "BRIGHT_DATA_API_KEY", api_key)


# ── get_bright_data_tools: URL / token handling ───────────────────────────────

@pytest.mark.asyncio
async def test_get_tools_uses_config_url_and_transport(bd, monkeypatch):
    state = _ClientState([_FakeTool("search_engine")])
    monkeypatch.setattr(bd, "MultiServerMCPClient", _make_fake_client_cls(state))
    _configure(monkeypatch, api_key=None)

    tools = await bd.get_bright_data_tools()

    assert [t.name for t in tools] == ["search_engine"]
    connection = state.constructed[0]["bright_data"]
    assert connection["url"] == "https://mcp.example/sse"
    assert connection["transport"] == "sse"
    assert connection["timeout"] == 600.0
    assert connection["sse_read_timeout"] == 600.0


@pytest.mark.asyncio
async def test_get_tools_appends_token_when_url_has_no_query(bd, monkeypatch):
    state = _ClientState([_FakeTool("search_engine")])
    monkeypatch.setattr(bd, "MultiServerMCPClient", _make_fake_client_cls(state))
    _configure(monkeypatch, url="https://mcp.example/sse", api_key="SECRET")

    await bd.get_bright_data_tools()

    assert state.constructed[0]["bright_data"]["url"] == "https://mcp.example/sse?token=SECRET"


@pytest.mark.asyncio
async def test_get_tools_keeps_existing_query_string(bd, monkeypatch):
    state = _ClientState([_FakeTool("search_engine")])
    monkeypatch.setattr(bd, "MultiServerMCPClient", _make_fake_client_cls(state))
    _configure(monkeypatch, url="https://mcp.example/sse?token=existing", api_key="SECRET")

    await bd.get_bright_data_tools()

    assert state.constructed[0]["bright_data"]["url"] == "https://mcp.example/sse?token=existing"


@pytest.mark.asyncio
async def test_get_tools_missing_url_raises(bd, monkeypatch):
    _configure(monkeypatch, url=None, api_key=None)
    with pytest.raises(RuntimeError, match="BRIGHT_DATA_MCP_URL is not configured"):
        await bd.get_bright_data_tools()


# ── get_bright_data_tools: retries / backoff ──────────────────────────────────

@pytest.mark.asyncio
async def test_get_tools_empty_list_raises_after_retries(bd, monkeypatch):
    state = _ClientState([])
    monkeypatch.setattr(bd, "MultiServerMCPClient", _make_fake_client_cls(state))
    _configure(monkeypatch)
    sleeps = _record_sleeps(monkeypatch)

    with pytest.raises(RuntimeError, match="0 tools"):
        await bd.get_bright_data_tools(max_retries=3, initial_backoff=0.1)

    assert len(state.constructed) == 3
    assert sleeps == [0.1, 0.2]


@pytest.mark.asyncio
async def test_get_tools_retries_with_exponential_backoff_then_succeeds(bd, monkeypatch):
    state = _ClientState([_FakeTool("search_engine")], fail_times=2, error="transient")
    monkeypatch.setattr(bd, "MultiServerMCPClient", _make_fake_client_cls(state))
    _configure(monkeypatch)
    sleeps = _record_sleeps(monkeypatch)

    tools = await bd.get_bright_data_tools(max_retries=5, initial_backoff=0.1)

    assert [t.name for t in tools] == ["search_engine"]
    assert len(state.constructed) == 3
    assert sleeps == [0.1, 0.2]


@pytest.mark.asyncio
async def test_get_tools_all_attempts_fail_raises_last_exception(bd, monkeypatch):
    state = _ClientState([_FakeTool("x")], fail_times=99, error="dead connection")
    monkeypatch.setattr(bd, "MultiServerMCPClient", _make_fake_client_cls(state))
    _configure(monkeypatch)
    sleeps = _record_sleeps(monkeypatch)

    with pytest.raises(RuntimeError, match="dead connection"):
        await bd.get_bright_data_tools(max_retries=2, initial_backoff=0.0)

    assert len(state.constructed) == 2
    assert sleeps == [0.0]


# ── get_bright_data_tools: caching ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_tools_caches_result(bd, monkeypatch):
    tools_in = [_FakeTool("search_engine"), _FakeTool("scrape_as_markdown")]
    state = _ClientState(tools_in)
    monkeypatch.setattr(bd, "MultiServerMCPClient", _make_fake_client_cls(state))
    _configure(monkeypatch)

    first = await bd.get_bright_data_tools()
    second = await bd.get_bright_data_tools()

    assert first is second
    assert bd._cached_tools is first
    assert len(state.constructed) == 1  # constructor called once


@pytest.mark.asyncio
async def test_get_tools_force_refresh_resets_and_reconnects(bd, monkeypatch):
    state = _ClientState([_FakeTool("search_engine")])
    monkeypatch.setattr(bd, "MultiServerMCPClient", _make_fake_client_cls(state))
    _configure(monkeypatch)

    first = await bd.get_bright_data_tools()
    old_client = bd._mcp_client

    second = await bd.get_bright_data_tools(force_refresh=True)

    assert first is not second
    assert state.aclose_calls == 1  # previous client closed
    assert len(state.constructed) == 2  # reconnected
    assert bd._mcp_client is not old_client


# ── reset_bright_data_tools ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reset_clears_globals_and_closes_client(bd):
    state = _ClientState([])
    bd._mcp_client = _make_fake_client_cls(state)({})
    bd._cached_tools = [_FakeTool("search_engine")]

    await bd.reset_bright_data_tools()

    assert bd._mcp_client is None
    assert bd._cached_tools is None
    assert state.aclose_calls == 1


@pytest.mark.asyncio
async def test_reset_tolerates_client_with_only_aexit(bd):
    calls = []

    class AexitOnlyClient:
        async def __aexit__(self, exc_type, exc, tb):
            calls.append((exc_type, exc, tb))

    bd._mcp_client = AexitOnlyClient()
    bd._cached_tools = [_FakeTool("x")]

    await bd.reset_bright_data_tools()

    assert calls == [(None, None, None)]
    assert bd._mcp_client is None
    assert bd._cached_tools is None


@pytest.mark.asyncio
async def test_reset_tolerates_close_that_raises(bd):
    class BadCloseClient:
        async def aclose(self):
            raise RuntimeError("close failed")

    bd._mcp_client = BadCloseClient()
    bd._cached_tools = [_FakeTool("x")]

    await bd.reset_bright_data_tools()  # must not propagate

    assert bd._mcp_client is None
    assert bd._cached_tools is None


# ── get_search_only_tools ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_search_only_tools_keeps_search_tools(bd, monkeypatch):
    tools_in = [_FakeTool("search_engine"), _FakeTool("scrape_as_markdown"), _FakeTool("web_search")]
    state = _ClientState(tools_in)
    monkeypatch.setattr(bd, "MultiServerMCPClient", _make_fake_client_cls(state))
    _configure(monkeypatch)

    result = await bd.get_search_only_tools()

    assert [t.name for t in result] == ["search_engine", "web_search"]


@pytest.mark.asyncio
async def test_get_search_only_tools_falls_back_to_all(bd, monkeypatch):
    tools_in = [_FakeTool("scrape_as_markdown"), _FakeTool("scrape_as_text")]
    state = _ClientState(tools_in)
    monkeypatch.setattr(bd, "MultiServerMCPClient", _make_fake_client_cls(state))
    _configure(monkeypatch)

    result = await bd.get_search_only_tools()

    assert result == tools_in


# ── _setup_quiet_exception_handler ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quiet_exception_handler_installs_once_and_swallows_mcp_chatter():
    loop = asyncio.get_running_loop()
    original_handler = loop.get_exception_handler()
    try:
        loop._mcp_handler_installed = False
        bright_data._setup_quiet_exception_handler()

        handler = loop.get_exception_handler()
        assert handler is not None
        assert getattr(loop, "_mcp_handler_installed") is True

        # Second call is a no-op: the installed handler is left in place.
        def sentinel(lp, ctx):
            return None

        loop.set_exception_handler(sentinel)
        bright_data._setup_quiet_exception_handler()
        assert loop.get_exception_handler() is sentinel

        # The captured handler swallows known MCP transport noise (message based).
        class FakeLoop:
            def __init__(self):
                self.delegated = []

            def default_exception_handler(self, context):
                self.delegated.append(context)

        fake_loop = FakeLoop()
        for message in ["post_writer closed", "RemoteProtocolError: peer", "Server disconnected"]:
            handler(fake_loop, {"message": message})
        assert fake_loop.delegated == []

        # ... and (exception based).
        handler(fake_loop, {"exception": RuntimeError("post_writer boom"), "message": "irrelevant"})
        assert fake_loop.delegated == []

        # Anything else is delegated to the default handler.
        benign = {"exception": ValueError("unrelated"), "message": "unrelated"}
        handler(fake_loop, benign)
        assert fake_loop.delegated == [benign]

        message_only = {"message": "some other transport issue"}
        handler(fake_loop, message_only)
        assert fake_loop.delegated == [benign, message_only]
    finally:
        loop.set_exception_handler(original_handler)
        if hasattr(loop, "_mcp_handler_installed"):
            del loop._mcp_handler_installed
