"""LangGraph nodes and graph construction for Contact Finder Agent."""

import asyncio
import json
import os
import re
import time
from typing import Literal
import httpx
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command

import config as app_config
from configuration import Configuration
from graph.state import AgentInputState, AgentState
from schemas.decision_maker_schema import GeneratedQuery, ResearchLoopDecision, DecisionMakerList, DecisionMaker
from prompts.contact_finder_prompts import (
    QUERY_GENERATOR_PROMPT,
    RESEARCH_LOOP_SYSTEM_PROMPT,
    LOOP_DECISION_PROMPT
)
from mcp_client.bright_data_client import get_bright_data_tools
from utils import get_chat_model, invoke_model_with_rate_limit_retry, get_today_str, truncate_tool_output
from output.excel_exporter import export_contacts_excel
from logging_ import log_print


def _emit(event_type: str, data: dict, component: str = "graph.contact_finder", level: str = "info") -> None:
    """Emit structured log event via shared pipeline logger if available."""
    try:
        from logging_utils.registry import emit_event
        emit_event(event_type, data, level=level, component=component)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# Node 1: LLM Query Generator Node
# ──────────────────────────────────────────────────────────────────────────────
async def llm_query_generator(state: AgentState, config: RunnableConfig) -> dict:
    t0 = time.time()
    company_name = state.get("company_name", "") or "Unknown Company"
    company_linkedin = state.get("company_linkedin", "") or "Not provided"
    company_website = state.get("company_website", "") or "Not provided"
    location = state.get("location", "") or "India"

    _emit("node_enter", {
        "node_name": "llm_query_generator",
        "step_num": 1,
        "description": "Generating SerpAPI search query for decision maker discovery",
        "company": company_name,
        "location": location,
    })
    log_print(f"\n[Company: {company_name}] 🟢 Entering Node 1: llm_query_generator")

    prompt_content = QUERY_GENERATOR_PROMPT.format(
        company_name=company_name,
        company_linkedin=company_linkedin,
        company_website=company_website,
        location=location,
        date=get_today_str()
    )

    configurable = Configuration.from_runnable_config(config)
    model_fn = lambda dep: get_chat_model(dep).with_structured_output(GeneratedQuery).with_retry(
        stop_after_attempt=configurable.max_structured_output_retries
    )

    response = await invoke_model_with_rate_limit_retry(model_fn, [HumanMessage(content=prompt_content)])
    query = response.query.strip()

    _emit("search_query", {
        "query_str": query,
        "source": "serp_query_generator",
        "company": company_name,
    })
    _emit("node_exit", {
        "node_name": "llm_query_generator",
        "step_num": 1,
        "duration_ms": int((time.time() - t0) * 1000),
        "output_summary": {"query": query},
    })
    log_print(f"[Company: {company_name}] ✅ Generated SerpAPI Query: '{query}'")
    return {"generated_query": query}


# ──────────────────────────────────────────────────────────────────────────────
# Node 2: SerpAPI Node
# ──────────────────────────────────────────────────────────────────────────────
async def serp_search(state: AgentState, config: RunnableConfig) -> dict:
    t0 = time.time()
    company_name = state.get("company_name", "") or "Unknown Company"
    _emit("node_enter", {
        "node_name": "serp_search",
        "step_num": 2,
        "description": "Executing SerpAPI query to discover decision maker candidates",
        "company": company_name,
    })
    log_print(f"\n[Company: {company_name}] 🟢 Entering Node 2: serp_search")
    query = state.get("generated_query", "")
    api_key = app_config.SERPAPI_API_KEY

    if not api_key:
        log_print(f"[Company: {company_name}] ⚠️ SERPAPI_API_KEY not configured in environment. Skipping SerpAPI execution.")
        return {"serp_raw_response": {}, "ai_overview": "SerpAPI API Key not configured."}

    log_print(f"[Company: {company_name}] 🔧 Executing SerpAPI query: '{query}'")

    params = {
        "q": query,
        "api_key": api_key,
        "engine": "google",
        "num": 10
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get("https://serpapi.com/search", params=params)
            resp.raise_for_status()
            raw_json = resp.json()
            
        log_print(f"[Company: {company_name}] ✅ SerpAPI call succeeded.")
        ai_overview = ""
        if "ai_overview" in raw_json:
            ai_data = raw_json["ai_overview"]
            if isinstance(ai_data, dict):
                ai_overview = ai_data.get("text", "") or json.dumps(ai_data)
            else:
                ai_overview = str(ai_data)
        elif "answer_box" in raw_json:
            ab = raw_json["answer_box"]
            ai_overview = ab.get("answer", "") or ab.get("snippet", "")
        
        if not ai_overview:
            organic = raw_json.get("organic_results", [])
            snippets = [f"- {item.get('title')}: {item.get('snippet')}" for item in organic[:5] if item.get("snippet")]
            ai_overview = "\n".join(snippets)

        log_print(f"[Company: {company_name}] 📝 Extracted AI Overview ({len(ai_overview)} chars)")
        _emit("node_exit", {
            "node_name": "serp_search",
            "step_num": 2,
            "duration_ms": int((time.time() - t0) * 1000),
            "output_summary": {"ai_overview_chars": len(ai_overview), "organic_results": len(raw_json.get("organic_results", []))},
        })
        return {
            "serp_raw_response": raw_json,
            "ai_overview": ai_overview
        }

    except Exception as e:
        _emit("tool_error", {"tool_name": "serp_search", "company": company_name, "error": str(e)}, level="warning")
        log_print(f"[Company: {company_name}] ❌ SerpAPI call failed: {e}")
        return {
            "serp_raw_response": {},
            "ai_overview": f"SerpAPI Error: {str(e)}"
        }


async def execute_tool_safely(tool, args, config, company_name: str = "Unknown Company", max_retries: int = 3):
    tool_name = getattr(tool, "name", str(tool))
    for attempt in range(1, max_retries + 1):
        try:
            return await tool.ainvoke(args, config)
        except Exception as e:
            err_str = str(e)
            err_lower = err_str.lower()
            is_connection_error = any(kw in err_lower for kw in [
                "remoteprotocolerror", "server disconnected", "connection", "closed", 
                "reset", "timeout", "502", "503", "504", "post_writer", "sse", "httpcore", "httpx"
            ])
            
            if is_connection_error and attempt < max_retries:
                log_print(f"[Company: {company_name}] ⚠️ Tool '{tool_name}' execution hit network/disconnection error (attempt {attempt}/{max_retries}): {err_str}")
                log_print(f"[Company: {company_name}] ⚡ Reconnecting Bright Data MCP instantly...")
                from mcp_client.bright_data_client import get_bright_data_tools, reset_bright_data_tools
                await reset_bright_data_tools()
                try:
                    fresh_tools = await get_bright_data_tools(force_refresh=True, initial_backoff=0.1)
                    matching = [t for t in fresh_tools if getattr(t, 'name', '') == tool_name]
                    if matching:
                        tool = matching[0]
                        log_print(f"[Company: {company_name}] 🚀 Retrying '{tool_name}' instantly with fresh connection...")
                        return await tool.ainvoke(args, config)
                except Exception as re_err:
                    log_print(f"[Company: {company_name}] ⚠️ Instant reconnect attempt failed: {re_err}")
            else:
                if attempt == max_retries or not is_connection_error:
                    log_print(f"[Company: {company_name}] ❌ Tool '{tool_name}' failed on attempt {attempt}: {err_str}")
                    return f"Error executing tool: {err_str}"
                await asyncio.sleep(0.1 * attempt)

# ──────────────────────────────────────────────────────────────────────────────
# Node 3: Research Loop Node (Conditional Self-Loop)
# ──────────────────────────────────────────────────────────────────────────────
def _parse_decision_makers_from_text(text: str) -> list[dict]:
    """Helper to extract decision maker candidate JSON structures from LLM/Tool output text."""
    extracted = []
    # Search for JSON blocks in output
    matches = re.findall(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    for match in matches:
        try:
            data = json.loads(match)
            if isinstance(data, list):
                extracted.extend(data)
            elif isinstance(data, dict):
                if "decision_makers" in data and isinstance(data["decision_makers"], list):
                    extracted.extend(data["decision_makers"])
                else:
                    extracted.append(data)
        except Exception:
            pass

    return extracted


async def research_loop(state: AgentState, config: RunnableConfig) -> Command[Literal["research_loop", "output_node"]]:
    t0 = time.time()
    company_name = state.get("company_name", "") or "Unknown Company"
    scrape_calls_used = state.get("scrape_calls_used", 0)
    decision_makers = state.get("decision_makers", []) or []
    loop_memory = state.get("loop_memory", []) or []
    location = state.get("location", "")
    
    _emit("node_enter", {
        "node_name": "research_loop",
        "step_num": 3,
        "description": f"BrightData research loop iteration {scrape_calls_used + 1}",
        "company": company_name,
        "iteration": scrape_calls_used + 1,
        "scrape_calls_used": scrape_calls_used,
        "decision_makers_count": len(decision_makers),
    })
    log_print(f"\n[Company: {company_name}] 🟢 Entering Node 3: research_loop (Call count: {scrape_calls_used}/{app_config.MAX_SCRAPE_CALLS})")

    # 1. Pre-Check Exit Conditions
    valid_dms_with_li = [
        dm for dm in decision_makers 
        if dm.get("name") and dm.get("linkedin_url") and "linkedin.com/in/" in dm.get("linkedin_url", "").lower()
    ]

    if scrape_calls_used >= app_config.MAX_SCRAPE_CALLS:
        log_print(f"[Company: {company_name}] 🛑 Scrape budget reached ({scrape_calls_used}/{app_config.MAX_SCRAPE_CALLS}). Moving to output_node.")
        _emit("node_exit", {"node_name": "research_loop", "step_num": 3, "company": company_name, "exit_reason": "budget_exhausted", "duration_ms": int((time.time() - t0) * 1000)})
        return Command(goto="output_node")

    if len(valid_dms_with_li) >= app_config.MAX_DECISION_MAKERS:
        log_print(f"[Company: {company_name}] 🎯 Target decision makers found ({len(valid_dms_with_li)}/{app_config.MAX_DECISION_MAKERS}). Moving to output_node.")
        _emit("node_exit", {"node_name": "research_loop", "step_num": 3, "company": company_name, "exit_reason": "target_reached", "duration_ms": int((time.time() - t0) * 1000)})
        return Command(goto="output_node")

    # 2. Prepare BrightData tools
    try:
        tools = await get_bright_data_tools()
    except Exception as e:
        log_print(f"[Company: {company_name}] ❌ Could not load BrightData tools: {e}")
        return Command(goto="output_node")

    tools_by_name = {tool.name: tool for tool in tools}

    # Format loop memory summary for prompt
    memory_summary = "\n".join([
        f"- Iteration {m.get('iteration')}: Tool '{m.get('tool_called')}' | DM Count: {len(m.get('new_dms', []))} | Reason: {m.get('reasoning')}"
        for m in loop_memory
    ]) if loop_memory else "None"

    formatted_dms = json.dumps(decision_makers, indent=2) if decision_makers else "None"

    system_prompt = RESEARCH_LOOP_SYSTEM_PROMPT.format(
        company_name=company_name,
        company_website=state.get("company_website", ""),
        company_linkedin=state.get("company_linkedin", ""),
        location=location,
        date=get_today_str(),
        ai_overview=state.get("ai_overview", "N/A"),
        decision_makers_found=formatted_dms,
        scrape_calls_used=scrape_calls_used,
        scrape_calls_remaining=app_config.MAX_SCRAPE_CALLS - scrape_calls_used,
        loop_memory_summary=memory_summary,
        max_decision_makers=app_config.MAX_DECISION_MAKERS
    )

    configurable = Configuration.from_runnable_config(config)
    model = get_chat_model().bind_tools(tools)

    log_print(f"[Company: {company_name}] 🔵 Selecting BrightData scraping action...")
    llm_response = await invoke_model_with_rate_limit_retry(
        model, 
        [SystemMessage(content=system_prompt), HumanMessage(content="Select and call the best BrightData scraping tool to find decision makers or missing LinkedIn URLs.")]
    )

    tool_calls = getattr(llm_response, "tool_calls", None) or []

    if not tool_calls:
        log_print(f"[Company: {company_name}] ⚠️ LLM returned no tool call. Evaluating exit decision...")
        # Evaluate if exit needed
        decision_model = get_chat_model().with_structured_output(ResearchLoopDecision)
        decision_prompt = LOOP_DECISION_PROMPT.format(
            company_name=company_name,
            location=location,
            max_decision_makers=app_config.MAX_DECISION_MAKERS,
            decision_makers_found=formatted_dms,
            scrape_calls_used=scrape_calls_used,
            max_scrape_calls=app_config.MAX_SCRAPE_CALLS,
            tool_output_preview="No tool executed in last step.",
            date=get_today_str()
        )
        decision = await invoke_model_with_rate_limit_retry(decision_model, [HumanMessage(content=decision_prompt)])
        log_print(f"[Company: {company_name}] 🧠 Status: {decision.status} | Reason: {decision.reasoning}")
        
        if decision.status == "NOT_NEEDED":
            return Command(goto="output_node")
        else:
            return Command(goto="research_loop")

    # Select the first tool call
    target_tool_call = tool_calls[0]
    tool_name = target_tool_call.get("name")
    tool_args = target_tool_call.get("args", {})

    # Guard: Rule violation check - prevent scraping LinkedIn personal profiles
    target_url = str(tool_args.get("url", "") or tool_args.get("link", "") or "")
    if "linkedin.com/in/" in target_url.lower():
        log_print(f"[Company: {company_name}] 🛑 Blocked scraping LinkedIn profile URL: {target_url}")
        new_memory_entry = {
            "iteration": scrape_calls_used + 1,
            "tool_called": tool_name,
            "tool_input": tool_args,
            "tool_output_preview": "BLOCKED: Scrape request to LinkedIn personal profile violated platform policy.",
            "new_dms": [],
            "reasoning": "Attempted forbidden LinkedIn profile scraping.",
            "decision": "NEEDED"
        }
        return Command(
            goto="research_loop",
            update={
                "scrape_calls_used": scrape_calls_used + 1,
                "loop_memory": [new_memory_entry]
            }
        )

    log_print(f"[Company: {company_name}] 🔧 BrightData Tool: {tool_name} | Args: {tool_args}")
    _emit("tool_start", {
        "tool_name": tool_name,
        "company": company_name,
        "args_preview": str(tool_args)[:200],
        "iteration": scrape_calls_used + 1,
    })
    
    # Execute Tool safely
    tool_output_str = ""
    selected_tool = tools_by_name.get(tool_name)
    t_tool = time.time()
    if selected_tool:
        tool_res = await execute_tool_safely(selected_tool, tool_args, config, company_name=company_name)
        tool_output_str = truncate_tool_output(tool_res)
        _emit("tool_end", {
            "tool_name": tool_name,
            "company": company_name,
            "output_chars": len(tool_output_str),
            "latency_ms": int((time.time() - t_tool) * 1000),
        })
        log_print(f"[Company: {company_name}] ✅ BrightData tool execution completed ({len(tool_output_str)} chars)")
    else:
        tool_output_str = f"Error: Tool '{tool_name}' not found."
        _emit("tool_error", {"tool_name": tool_name, "error": tool_output_str, "company": company_name}, level="warning")
        log_print(f"[Company: {company_name}] ❌ {tool_output_str}")

    new_scrape_calls_used = scrape_calls_used + 1

    # Use LLM to parse out any discovered decision makers from tool output
    extraction_prompt = f"""
    Analyze the following scraped text from BrightData tool '{tool_name}' for company '{company_name}' (Location: {location}):
    
    <Scraped Content>
    {tool_output_str[:15000]}
    </Scraped Content>
    
    Extract any decision makers (CEO, Founder, Co-Founder, VP, Director, Head of, etc.) along with their job title and individual LinkedIn profile URL (must contain linkedin.com/in/).
    Do NOT include generic company LinkedIn URLs.
    
    Return structured output matching the DecisionMakerList schema.
    """
    
    extracted_dms = []
    try:
        extractor_model = get_chat_model().with_structured_output(DecisionMakerList)
        extraction_res = await invoke_model_with_rate_limit_retry(extractor_model, [HumanMessage(content=extraction_prompt)])
        for dm in extraction_res.decision_makers:
            extracted_dms.append({
                "name": dm.name,
                "position": dm.position,
                "linkedin_url": dm.linkedin_url
            })
    except Exception as e:
        log_print(f"[Company: {company_name}] ⚠️ Failed structured extraction from tool output: {e}")

    # Deduplicate extracted decision makers against current state
    existing_urls = {dm.get("linkedin_url", "").lower() for dm in decision_makers if dm.get("linkedin_url")}
    existing_names = {dm.get("name", "").lower() for dm in decision_makers if dm.get("name")}
    
    new_unique_dms = []
    for dm in extracted_dms:
        li = dm.get("linkedin_url", "").lower()
        nm = dm.get("name", "").lower()
        if li and li not in existing_urls and nm not in existing_names:
            new_unique_dms.append(dm)
            existing_urls.add(li)
            existing_names.add(nm)

    log_print(f"[Company: {company_name}] 👥 Discovered {len(new_unique_dms)} new unique decision makers.")

    # LLM Node Evaluation: NEEDED vs NOT_NEEDED
    combined_dms = decision_makers + new_unique_dms
    decision_model = get_chat_model().with_structured_output(ResearchLoopDecision)
    decision_prompt = LOOP_DECISION_PROMPT.format(
        company_name=company_name,
        location=location,
        max_decision_makers=app_config.MAX_DECISION_MAKERS,
        decision_makers_found=json.dumps(combined_dms, indent=2),
        scrape_calls_used=new_scrape_calls_used,
        max_scrape_calls=app_config.MAX_SCRAPE_CALLS,
        tool_output_preview=tool_output_str[:1000],
        date=get_today_str()
    )

    decision_res = await invoke_model_with_rate_limit_retry(decision_model, [HumanMessage(content=decision_prompt)])
    log_print(f"[Company: {company_name}] 🧠 Loop Verdict: {decision_res.status} | Rationale: {decision_res.reasoning}")

    memory_entry = {
        "iteration": new_scrape_calls_used,
        "tool_called": tool_name,
        "tool_input": tool_args,
        "tool_output_preview": tool_output_str[:500],
        "new_dms": new_unique_dms,
        "reasoning": decision_res.reasoning,
        "decision": decision_res.status
    }

    state_update = {
        "decision_makers": new_unique_dms,
        "scrape_calls_used": new_scrape_calls_used,
        "loop_memory": [memory_entry]
    }

    # Emit contact_found events for new unique decision makers
    for dm in new_unique_dms:
        _emit("contact_found", {
            "person_name": dm.get("name"),
            "role": dm.get("position"),
            "linkedin_url": dm.get("linkedin_url"),
            "company": company_name,
            "source": tool_name,
        })

    if decision_res.status == "NOT_NEEDED" or new_scrape_calls_used >= app_config.MAX_SCRAPE_CALLS or len(combined_dms) >= app_config.MAX_DECISION_MAKERS:
        log_print(f"[Company: {company_name}] ➡️ Exiting research_loop to output_node.")
        _emit("node_exit", {
            "node_name": "research_loop",
            "step_num": 3,
            "company": company_name,
            "exit_reason": decision_res.status,
            "new_dms": len(new_unique_dms),
            "total_dms": len(combined_dms),
            "iteration": new_scrape_calls_used,
            "duration_ms": int((time.time() - t0) * 1000),
        })
        return Command(goto="output_node", update=state_update)

    log_print(f"[Company: {company_name}] 🔁 Continuing research_loop...")
    _emit("node_exit", {
        "node_name": "research_loop",
        "step_num": 3,
        "company": company_name,
        "exit_reason": "continuing",
        "new_dms": len(new_unique_dms),
        "iteration": new_scrape_calls_used,
        "duration_ms": int((time.time() - t0) * 1000),
    })
    return Command(goto="research_loop", update=state_update)


# ──────────────────────────────────────────────────────────────────────────────
# Node 4: Output Node
# ──────────────────────────────────────────────────────────────────────────────
async def output_node(state: AgentState, config: RunnableConfig) -> dict:
    t0 = time.time()
    company_name = state.get("company_name", "") or "Unknown Company"
    _emit("node_enter", {
        "node_name": "output_node",
        "step_num": 4,
        "description": "Exporting decision makers to Excel & JSON",
        "company": company_name,
    })
    log_print(f"\n[Company: {company_name}] 🟢 Entering Node 4: output_node")

    company_website = state.get("company_website", "")
    company_linkedin = state.get("company_linkedin", "")
    location = state.get("location", "")
    session_id = state.get("session_id", "default_session")
    decision_makers = state.get("decision_makers", []) or []

    # Final Deduplication & Clean-up
    seen_urls = set()
    cleaned_dms = []
    for dm in decision_makers:
        url = dm.get("linkedin_url", "").strip()
        if url and url not in seen_urls:
            seen_urls.add(url)
            cleaned_dms.append(dm)

    

    log_print(f"[Company: {company_name}] 📊 Exporting {len(cleaned_dms)} decision makers to Excel...")
    excel_path = export_contacts_excel(
        company_name=company_name,
        company_website=company_website,
        company_linkedin=company_linkedin,
        location=location,
        decision_makers=cleaned_dms,
        session_id=session_id
    )
    log_print(f"[Company: {company_name}] ✅ Excel saved to: {excel_path}")

    # Write persistent JSON state store
    os.makedirs(app_config.OUTPUT_DIR, exist_ok=True)
    json_path = os.path.join(app_config.OUTPUT_DIR, f"agent_state_{session_id}.json")
    
    full_state_export = {
        "session_id": session_id,
        "company_name": company_name,
        "company_website": company_website,
        "company_linkedin": company_linkedin,
        "location": location,
        "generated_query": state.get("generated_query", ""),
        "ai_overview": state.get("ai_overview", ""),
        "serp_raw_response": state.get("serp_raw_response", {}),
        "scrape_calls_used": state.get("scrape_calls_used", 0),
        "decision_makers": cleaned_dms,
        "loop_memory": state.get("loop_memory", [])
    }

    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(full_state_export, f, indent=2, ensure_ascii=False)
        log_print(f"[Company: {company_name}] 💾 Full Agent State JSON saved to: {json_path}")
    except Exception as e:
        log_print(f"[Company: {company_name}] ❌ Failed to write JSON agent state: {e}")

    _emit("node_exit", {
        "node_name": "output_node",
        "step_num": 4,
        "company": company_name,
        "duration_ms": int((time.time() - t0) * 1000),
        "output_summary": {
            "decision_makers_count": len(cleaned_dms),
            "excel_path": excel_path,
            "json_path": json_path,
        },
    })
    return {}


# ──────────────────────────────────────────────────────────────────────────────
# LangGraph Builder Construction
# ──────────────────────────────────────────────────────────────────────────────
contact_finder_builder = StateGraph(
    AgentState, 
    input=AgentInputState, 
    config_schema=Configuration
)

contact_finder_builder.add_node("llm_query_generator", llm_query_generator)
contact_finder_builder.add_node("serp_search", serp_search)
contact_finder_builder.add_node("research_loop", research_loop)
contact_finder_builder.add_node("output_node", output_node)

contact_finder_builder.add_edge(START, "llm_query_generator")
contact_finder_builder.add_edge("llm_query_generator", "serp_search")
contact_finder_builder.add_edge("serp_search", "research_loop")
contact_finder_builder.add_edge("output_node", END)

contact_finder = contact_finder_builder.compile()
