"""Verification Subgraph for Step 6 (Supervisor + Researcher Architecture)."""

import asyncio
import time
from typing import Literal
import json
import re


def _emit(event_type: str, data: dict, component: str = "graph.verifier_graph", level: str = "info") -> None:
    """Emit a structured log event via the shared pipeline logger if available."""
    try:
        from logging_utils.registry import emit_event
        emit_event(event_type, data, level=level, component=component)
    except Exception:
        pass

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    filter_messages,
    get_buffer_string,
)
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from configuration import Configuration
from prompts.verifier_prompt import (
    compress_verifier_human_message,
    compress_verifier_system_prompt,
    final_verification_report_prompt,
    lead_verifier_supervisor_prompt,
    verifier_researcher_prompt,
)
from graph.state import (
    ConductResearch,
    ResearchComplete,
    ResearcherOutputState,
    ResearcherState,
    SupervisorState,
)
from utils import (
    get_model_token_limit,
    get_today_str,
    is_token_limit_exceeded,
    remove_up_to_last_ai_message,
    think_tool,
    get_chat_model,
    invoke_model_with_rate_limit_retry,
    truncate_tool_output
)
from mcp_client.bright_data_client import get_search_only_tools

def _extract_company_name_from_research_state(state: dict) -> str:
    topic = state.get("research_topic", "")
    match = re.search(r"Company Name:\s*(.+)", topic)
    if match:
        return match.group(1).strip()
    return ""

async def execute_tool_safely(tool, args, config, company_name: str = "", max_retries: int = 3):
    tool_name = getattr(tool, "name", str(tool))
    tag = f"[Company: {company_name}] " if company_name else ""
    _emit("tool_start", {"tool_name": tool_name, "company": company_name, "attempt": 1})
    t0 = time.time()
    for attempt in range(1, max_retries + 1):
        try:
            result = await tool.ainvoke(args, config)
            _emit("tool_end", {"tool_name": tool_name, "company": company_name, "latency_ms": int((time.time() - t0) * 1000)})
            return result
        except Exception as e:
            err_str = str(e)
            err_lower = err_str.lower()
            is_connection_error = any(kw in err_lower for kw in [
                "remoteprotocolerror", "server disconnected", "connection", "closed", 
                "reset", "timeout", "502", "503", "504", "post_writer", "sse", "httpcore", "httpx"
            ])
            
            if is_connection_error and attempt < max_retries:
                _emit("mcp_error", {"server": "bright_data", "tool": tool_name, "error": err_str, "attempt": attempt, "company": company_name}, level="warning")
                print(f"⚠️ {tag}Tool '{tool_name}' hit network error (attempt {attempt}/{max_retries}): {err_str}")
                from mcp_client.bright_data_client import get_search_only_tools, reset_bright_data_tools
                await reset_bright_data_tools()
                try:
                    fresh_tools = await get_search_only_tools(force_refresh=True, initial_backoff=0.1)
                    matching = [t for t in fresh_tools if getattr(t, 'name', '') == tool_name]
                    if matching:
                        tool = matching[0]
                        result = await tool.ainvoke(args, config)
                        _emit("tool_end", {"tool_name": tool_name, "company": company_name, "latency_ms": int((time.time() - t0) * 1000), "reconnected": True})
                        return result
                except Exception as re_err:
                    _emit("mcp_error", {"server": "bright_data", "error": str(re_err), "attempt": attempt, "company": company_name}, level="warning")
            else:
                if attempt == max_retries or not is_connection_error:
                    _emit("tool_error", {"tool_name": tool_name, "error": err_str, "company": company_name, "attempt": attempt}, level="error")
                    return f"Error executing tool: {err_str}"
                await asyncio.sleep(0.1 * attempt)

# ----------------
# Researcher Node & Subgraph
# ----------------

async def verifier_researcher(state: ResearcherState, config: RunnableConfig) -> Command[Literal["verifier_researcher_tools"]]:
    configurable = Configuration.from_runnable_config(config)
    researcher_messages = state.get("researcher_messages", [])
    
    # Use search-only tools for verification
    search_tools = await get_search_only_tools()
    all_tools = search_tools + [think_tool]
    
    researcher_prompt = verifier_researcher_prompt.format(
        mcp_prompt=configurable.verifier_model or ""
    )
    
    research_model_fn = lambda dep: get_chat_model(dep).bind_tools(all_tools).with_retry(stop_after_attempt=configurable.max_structured_output_retries)
    
    messages = [SystemMessage(content=researcher_prompt)] + researcher_messages
    response = await invoke_model_with_rate_limit_retry(research_model_fn, messages)
    
    return Command(
        goto="verifier_researcher_tools",
        update={
            "researcher_messages": [response],
            "tool_call_iterations": state.get("tool_call_iterations", 0) + 1
        }
    )

async def verifier_researcher_tools(state: ResearcherState, config: RunnableConfig) -> Command[Literal["verifier_researcher", "compress_verifier_research"]]:
    configurable = Configuration.from_runnable_config(config)
    researcher_messages = state.get("researcher_messages", [])
    if not researcher_messages:
        return Command(goto="compress_verifier_research")
        
    most_recent_message = researcher_messages[-1]
    tool_calls = getattr(most_recent_message, "tool_calls", None) or []
    
    if not tool_calls:
        return Command(goto="compress_verifier_research")
    
    search_tools = await get_search_only_tools()
    all_tools = search_tools + [think_tool]
    tools_by_name = {
        t.name if hasattr(t, "name") else t.get("name", "web_search"): t 
        for t in all_tools
    }
    
    comp_name = _extract_company_name_from_research_state(state)
    tool_execution_tasks = []
    for tool_call in tool_calls:
        t_name = tool_call.get("name")
        args = tool_call.get("args", {})
        if t_name in tools_by_name:
            tool_execution_tasks.append(execute_tool_safely(tools_by_name[t_name], args, config, company_name=comp_name))
        elif t_name == "ResearchComplete":
            async def _dummy_complete():
                return "Research complete."
            tool_execution_tasks.append(_dummy_complete())
        else:
            async def _dummy_unknown(tn=t_name):
                return f"Executed tool {tn}"
            tool_execution_tasks.append(_dummy_unknown())

    observations = await asyncio.gather(*tool_execution_tasks)
    
    tool_outputs = [
        ToolMessage(
            content=truncate_tool_output(obs),
            name=tool_call.get("name", "unknown"),
            tool_call_id=tool_call["id"]
        ) 
        for obs, tool_call in zip(observations, tool_calls)
    ]
    
    exceeded_iterations = state.get("tool_call_iterations", 0) >= configurable.max_react_tool_calls
    research_complete_called = any(
        tool_call.get("name") == "ResearchComplete" 
        for tool_call in tool_calls
    )
    
    if exceeded_iterations or research_complete_called:
        return Command(
            goto="compress_verifier_research",
            update={"researcher_messages": tool_outputs}
        )
    
    return Command(
        goto="verifier_researcher",
        update={"researcher_messages": tool_outputs}
    )

async def compress_verifier_research(state: ResearcherState, config: RunnableConfig):
    configurable = Configuration.from_runnable_config(config)
    researcher_messages = state.get("researcher_messages", [])
    researcher_messages.append(HumanMessage(content=compress_verifier_human_message))
    
    try:
        compression_prompt = compress_verifier_system_prompt
        messages = [SystemMessage(content=compression_prompt)] + researcher_messages
        response = await invoke_model_with_rate_limit_retry(get_chat_model, messages)
        
        raw_notes_content = "\n".join([
            str(message.content) 
            for message in filter_messages(researcher_messages, include_types=["tool", "ai"])
            if message and getattr(message, "content", None) is not None
        ])
        
        return {
            "compressed_research": str(response.content) if response and response.content else "",
            "raw_notes": [raw_notes_content]
        }
    except Exception as e:
        return {
            "compressed_research": f"Error synthesizing research: {e}",
            "raw_notes": []
        }

# Researcher Subgraph Construction
researcher_builder = StateGraph(
    ResearcherState, 
    output_schema=ResearcherOutputState, 
    context_schema=Configuration
)
researcher_builder.add_node("verifier_researcher", verifier_researcher)
researcher_builder.add_node("verifier_researcher_tools", verifier_researcher_tools)
researcher_builder.add_node("compress_verifier_research", compress_verifier_research)
researcher_builder.add_edge(START, "verifier_researcher")
researcher_builder.add_edge("compress_verifier_research", END)
researcher_subgraph = researcher_builder.compile()

# ----------------
# Supervisor Node & Subgraph
# ----------------

async def verifier_supervisor(state: SupervisorState, config: RunnableConfig) -> Command[Literal["verifier_supervisor_tools"]]:
    iteration = state.get('research_iterations', 0) + 1
    _emit("node_enter", {
        "node_name": "verifier_supervisor",
        "step_num": 5,
        "description": f"Verification Supervisor iteration {iteration}",
        "iteration": iteration,
    })
    print(f"[FLOW] 🟢 Verification Supervisor (Iteration {iteration})")
    try:
        configurable = Configuration.from_runnable_config(config)
        lead_verifier_tools = [ConductResearch, ResearchComplete, think_tool]
        
        model_fn = lambda dep: get_chat_model(dep).bind_tools(lead_verifier_tools).with_retry(stop_after_attempt=configurable.max_structured_output_retries)
        
        supervisor_messages = state.get("supervisor_messages", [])
        response = await invoke_model_with_rate_limit_retry(model_fn, supervisor_messages)
        
        _emit("node_exit", {"node_name": "verifier_supervisor", "step_num": 5, "iteration": iteration})
        return Command(
            goto="verifier_supervisor_tools",
            update={
                "supervisor_messages": [response],
                "research_iterations": state.get("research_iterations", 0) + 1
            }
        )
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        _emit("pipeline_error", {"error": str(e), "traceback": tb, "node": "verifier_supervisor"}, level="error")
        print(f"[ERROR] ❌ Exception in verifier_supervisor:\n{tb}")
        raise e

async def verifier_supervisor_tools(state: SupervisorState, config: RunnableConfig) -> Command[Literal["verifier_supervisor", "__end__"]]:
    configurable = Configuration.from_runnable_config(config)
    supervisor_messages = state.get("supervisor_messages", [])
    research_iterations = state.get("research_iterations", 0)
    most_recent_message = supervisor_messages[-1] if supervisor_messages else None
    
    if not most_recent_message:
        return Command(goto="verifier_supervisor")

    tool_calls = getattr(most_recent_message, "tool_calls", None) or []
    no_tool_calls = not tool_calls
    has_conducted_research = any(
        isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None) and any(tc.get("name") == "ConductResearch" for tc in (msg.tool_calls or []))
        for msg in supervisor_messages
    )
    
    if no_tool_calls and not has_conducted_research:
        return Command(
            goto="verifier_supervisor",
            update={
                "supervisor_messages": [
                    HumanMessage(content="System Warning: Call 'ConductResearch' to delegate verification tasks to researchers.")
                ]
            }
        )

    conduct_research_calls = [
        tool_call for tool_call in tool_calls 
        if tool_call.get("name") == "ConductResearch"
    ]
    allowed_calls = conduct_research_calls[:configurable.max_concurrent_research_units]

    tool_results = []
    if allowed_calls:
        research_tasks = []
        for tool_call in allowed_calls:
            c_args = tool_call.get("args", {})
            comp_name = c_args.get("company_name", "") or c_args.get("research_topic", "")
            comp_web = c_args.get("website", "")
            comp_desc = c_args.get("description", "") or c_args.get("business_summary", "") or "N/A"
            topic = c_args.get("research_topic", "")
            
            prompt_content = (
                f"Search Official LinkedIn for Candidate Company (1 Company Per Run):\n"
                f"- Company Name: {comp_name}\n"
                f"- Official Website: {comp_web}\n"
                f"- Company Description: {comp_desc}\n"
                f"- Task Details: {topic}\n\n"
                f"Instructions: PRIORITIZE BATCH SEARCH QUERIES! Perform web search using structured queries combining Company Name, Website, and site filter (e.g. '\"{comp_name}\" \"{comp_web}\" site:linkedin.com/company'). "
                f"Extract the exact official LinkedIn company URL from search results. Output:\n"
                f"Company Name: {comp_name}\n"
                f"Official Website: {comp_web}\n"
                f"Company Description: {comp_desc}\n"
                f"Verified LinkedIn URL: <exact URL from search or NOT FOUND>\n"
                f"LinkedIn Confirmed: Yes/No"
            )
            
            research_tasks.append(
                researcher_subgraph.ainvoke({
                    "researcher_messages": [
                        HumanMessage(content=prompt_content)
                    ],
                    "research_topic": prompt_content
                }, config)
            )
        tool_results = await asyncio.gather(*research_tasks)

    research_res_by_id = {
        tc["id"]: res for tc, res in zip(allowed_calls, tool_results)
    }

    all_tool_messages = []
    for tool_call in tool_calls:
        t_name = tool_call.get("name")
        c_id = tool_call.get("id")
        args = tool_call.get("args", {})
        
        if t_name == "ConductResearch":
            if c_id in research_res_by_id:
                obs = research_res_by_id[c_id]
                content_str = truncate_tool_output(obs.get("compressed_research", "") if isinstance(obs, dict) else str(obs))
            else:
                content_str = "[Notice: Concurrency limit reached for this round. Task deferred.]"
            all_tool_messages.append(ToolMessage(
                content=content_str,
                name="ConductResearch",
                tool_call_id=c_id
            ))
        elif t_name == "think_tool":
            reflection = args.get("reflection", "") if isinstance(args, dict) else str(args)
            all_tool_messages.append(ToolMessage(
                content=f"Reflection recorded: {reflection}",
                name="think_tool",
                tool_call_id=c_id
            ))
        elif t_name == "ResearchComplete":
            all_tool_messages.append(ToolMessage(
                content="Research marked complete.",
                name="ResearchComplete",
                tool_call_id=c_id
            ))
        else:
            all_tool_messages.append(ToolMessage(
                content=f"Executed tool {t_name}",
                name=t_name or "unknown",
                tool_call_id=c_id
            ))

    raw_notes_list = []
    for observation in tool_results:
        if isinstance(observation, dict):
            notes_sub = observation.get("raw_notes") or []
            if isinstance(notes_sub, list):
                raw_notes_list.extend([str(n) for n in notes_sub if n is not None])

    exceeded_allowed_iterations = research_iterations > configurable.max_verifier_iterations
    research_complete_tool_call = any(
        tool_call.get("name") == "ResearchComplete" 
        for tool_call in tool_calls
    )

    if exceeded_allowed_iterations or research_complete_tool_call or (no_tool_calls and has_conducted_research):
        combined_msgs = list(supervisor_messages) + all_tool_messages
        notes_collected = [
            msg.content for msg in combined_msgs
            if getattr(msg, "type", "") == "tool" and getattr(msg, "name", "") == "ConductResearch"
        ]
        
        update_payload = {
            "supervisor_messages": all_tool_messages,
            "notes": notes_collected,
            "research_brief": state.get("research_brief", "")
        }
        if raw_notes_list:
            update_payload["raw_notes"] = ["\n".join(raw_notes_list)]
            
        return Command(
            goto=END,
            update=update_payload
        )

    update_payload = {"supervisor_messages": all_tool_messages}
    if raw_notes_list:
        update_payload["raw_notes"] = ["\n".join(raw_notes_list)]

    return Command(
        goto="verifier_supervisor",
        update=update_payload
    )

# Supervisor Subgraph Construction
verifier_supervisor_builder = StateGraph(SupervisorState, context_schema=Configuration)
verifier_supervisor_builder.add_node("verifier_supervisor", verifier_supervisor)
verifier_supervisor_builder.add_node("verifier_supervisor_tools", verifier_supervisor_tools)
verifier_supervisor_builder.add_edge(START, "verifier_supervisor")
verifier_supervisor_subgraph = verifier_supervisor_builder.compile()
