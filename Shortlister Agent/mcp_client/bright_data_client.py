import os
import asyncio
from typing import List
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import BaseTool
import config

_mcp_client = None
_cached_tools = None
_mcp_lock = asyncio.Lock()

def _setup_quiet_exception_handler():
    try:
        loop = asyncio.get_running_loop()
        if getattr(loop, "_mcp_handler_installed", False):
            return
        
        def custom_handler(lp, context):
            exc = context.get("exception")
            msg = str(context.get("message", ""))
            err_str = str(exc) if exc else msg
            err_lower = err_str.lower()
            if any(kw in err_lower for kw in ["post_writer", "remoteprotocolerror", "server disconnected"]):
                print("⚡ [MCP Transport] Server dropped idle connection stream (auto-reconnecting on demand).")
                return
            lp.default_exception_handler(context)

        loop.set_exception_handler(custom_handler)
        loop._mcp_handler_installed = True
    except Exception:
        pass

async def reset_bright_data_tools():
    """Resets cached MCP tools and client so subsequent calls establish a new connection."""
    global _mcp_client, _cached_tools
    print("🔄 [MCP Client] Resetting cached Bright Data tools and client connection...")
    if _mcp_client is not None:
        try:
            if hasattr(_mcp_client, "aclose"):
                await _mcp_client.aclose()
            elif hasattr(_mcp_client, "__aexit__"):
                await _mcp_client.__aexit__(None, None, None)
        except Exception as e:
            print(f"⚠️ Error closing previous MCP client: {e}")
    _mcp_client = None
    _cached_tools = None

async def get_bright_data_tools(max_retries: int = 5, initial_backoff: float = 0.1, force_refresh: bool = False) -> List[BaseTool]:
    """
    Connects to the Bright Data MCP server via HTTP/SSE and returns all available tools
    as LangChain-compatible BaseTool objects. Caches the tools for subsequent calls.
    """
    global _mcp_client, _cached_tools
    _setup_quiet_exception_handler()
    
    if force_refresh:
        await reset_bright_data_tools()
        
    if _cached_tools is not None:
        return _cached_tools

    async with _mcp_lock:
        if _cached_tools is not None and not force_refresh:
            return _cached_tools
            
        url = config.BRIGHT_DATA_MCP_URL
        if not url:
            print("MCP Failed: BRIGHT_DATA_MCP_URL is not set.")
            raise RuntimeError("MCP Failed: BRIGHT_DATA_MCP_URL is not configured in environment.")
        
        if "?" not in url and config.BRIGHT_DATA_API_KEY:
            url = f"{url}?token={config.BRIGHT_DATA_API_KEY}"
            
        backoff = initial_backoff
        last_exception = None

        for attempt in range(1, max_retries + 1):
            try:
                print(f"Connecting to Bright Data MCP server (attempt {attempt}/{max_retries})...")
                client = MultiServerMCPClient({
                    "bright_data": {
                        "url": url,
                        "transport": "sse",
                        "timeout": 600.0,
                        "sse_read_timeout": 600.0,
                    }
                })
                tools = await client.get_tools()
                if not tools:
                    print("MCP Failed: Server returned 0 tools.")
                    raise RuntimeError("MCP Failed: Server returned 0 tools.")
                
                _mcp_client = client
                _cached_tools = tools
                print(f"Successfully connected to Bright Data MCP server. Loaded {len(tools)} tools.")
                return tools
            except Exception as e:
                last_exception = e
                print(f"⚠️ Bright Data MCP connection attempt {attempt}/{max_retries} failed: {e}")
                if attempt < max_retries:
                    print(f"Retrying in {backoff}s...")
                    await asyncio.sleep(backoff)
                    backoff *= 2
                else:
                    print(f"MCP Failed: All {max_retries} connection attempts failed.")

        raise RuntimeError(f"MCP Failed: {last_exception}") from last_exception

async def get_search_only_tools(max_retries: int = 5, initial_backoff: float = 0.1, force_refresh: bool = False) -> List[BaseTool]:
    """
    Returns only Bright Data search tools (excludes scrape-as-markdown / scrape-as-text tools).
    Used by LinkedIn verifier node as specified in Step 5 requirement.
    """
    all_tools = await get_bright_data_tools(max_retries, initial_backoff, force_refresh=force_refresh)
    search_tools = [t for t in all_tools if 'search' in getattr(t, 'name', '').lower()]
    if not search_tools:
        # Fallback to all tools if name matching is broader
        return all_tools
    return search_tools
