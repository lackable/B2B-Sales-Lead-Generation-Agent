"""Main LangGraph Pipeline for Shortlister Agent (Steps 1 to 6) with structured logging."""

import asyncio
import os
import re
import sys
import time
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
import yfinance as yf

from configuration import Configuration
from prompts.query_formulator_prompt import query_formulator_instructions
from graph.state import (
    ShortlisterState,
    ScreenerQuery,
    CompanyRecord,
)
from graph.verifier_graph import verifier_supervisor_subgraph, researcher_subgraph
from graph.linkedin_finder_subgraph import run_linkedin_finder_subgraph
from utils import (
    get_chat_model,
    invoke_model_with_rate_limit_retry,
    convert_ticker,
    fallback_financedatabase_website,
    get_today_str,
)
from output.report_saver import save_all


def _emit(event_type: str, data: dict, component: str = "graph.shortlister", level: str = "info") -> None:
    """Emit a structured event if the logger is available; silently no-op otherwise."""
    try:
        from logging_utils.registry import emit_event
        emit_event(event_type, data, level=level, component=component)
    except Exception:
        pass


def get_now_str() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────────────────────────────────────────────────────────
# Node 1: Query Formulator
# ─────────────────────────────────────────────────────────────────────────────

async def query_formulator(state: ShortlisterState, config: RunnableConfig) -> Command[Literal["screener_fetch"]]:
    t0 = time.time()
    _emit("node_enter", {
        "node_name": "query_formulator",
        "step_num": 1,
        "description": "Translating natural language prompt into structured TradingView Screener parameters",
        "state_keys_present": list(state.keys()),
    })

    configurable = Configuration.from_runnable_config(config)
    messages = state.get("messages", [])
    user_input = messages[-1].content if messages else "Technology companies in India"

    _emit("progress", {
        "stage": "query_formulator",
        "progress_pct": 5,
        "message": f"Formulating query for: \"{user_input[:80]}\"",
    })

    prompt = query_formulator_instructions.format(user_input=user_input)
    model_fn = lambda dep: get_chat_model(dep).with_structured_output(ScreenerQuery).with_retry(
        stop_after_attempt=configurable.max_structured_output_retries
    )

    query_res: ScreenerQuery = await invoke_model_with_rate_limit_retry(model_fn, [HumanMessage(content=prompt)])

    _emit("node_exit", {
        "node_name": "query_formulator",
        "step_num": 1,
        "duration_ms": int((time.time() - t0) * 1000),
        "output_summary": {
            "sector": query_res.sector,
            "industry": query_res.industry,
            "market": query_res.market,
            "location": query_res.location,
            "revenue_min": query_res.revenue_min,
            "revenue_max": query_res.revenue_max,
            "limit": query_res.limit,
            # Slots for visualizer QueryScene
            "slots": {
                "SECTOR": query_res.sector or "",
                "INDUSTRY": query_res.industry or "All",
                "MARKET": query_res.market or "india",
                "LOCATION": query_res.location or "India",
                "LIMIT": str(query_res.limit),
            },
        },
    })

    print(f"\n✅ [{get_now_str()}] [Structured Screener Query Extracted]:")
    print(f"   ├─ Sector (Req): {query_res.sector}")
    print(f"   ├─ Industry (Opt): {query_res.industry or 'None (All in Sector)'}")
    print(f"   ├─ Market:      {query_res.market}")
    print(f"   ├─ Location:    {query_res.location}")
    print(f"   └─ Target Fetch Limit: {query_res.limit} companies")

    return Command(
        goto="screener_fetch",
        update={"screener_query": query_res}
    )


# ─────────────────────────────────────────────────────────────────────────────
# Node 2: Screener Fetch
# ─────────────────────────────────────────────────────────────────────────────

async def screener_fetch(state: ShortlisterState, config: RunnableConfig) -> Command[Literal["yfinance_enricher"]]:
    t0 = time.time()
    query_res: ScreenerQuery = state.get("screener_query")

    _emit("node_enter", {
        "node_name": "screener_fetch",
        "step_num": 2,
        "description": "Executing TradingView Screener API query programmatically",
        "state_keys_present": list(state.keys()),
    })
    _emit("progress", {
        "stage": "screener_fetch",
        "progress_pct": 15,
        "message": f"Connecting to TradingView for market='{getattr(query_res, 'market', 'india')}'",
    })

    try:
        from tradingview_screener import Query, col

        market = (query_res.market or "india").lower()
        limit = query_res.limit or 60

        print(f"📡 [{get_now_str()}] [API Query]: Connecting to TradingView scanner for market='{market}', limit={limit}...")
        print(f"   Filters -> Sector: '{query_res.sector}' | Industry: '{query_res.industry}'")

        q = Query().set_markets(market).select('name', 'sector', 'industry', 'total_revenue_ttm', 'net_income_ttm')
        where_conditions = []

        if query_res.sector:
            where_conditions.append(col('sector') == query_res.sector)
        if query_res.industry:
            where_conditions.append(col('industry') == query_res.industry)
        if query_res.revenue_min is not None and query_res.revenue_max is not None:
            where_conditions.append(col('total_revenue_ttm').between(query_res.revenue_min, query_res.revenue_max))
        elif query_res.revenue_min is not None:
            where_conditions.append(col('total_revenue_ttm') >= query_res.revenue_min)
        elif query_res.revenue_max is not None:
            where_conditions.append(col('total_revenue_ttm') <= query_res.revenue_max)
        if query_res.profit_min is not None and query_res.profit_max is not None:
            where_conditions.append(col('net_income_ttm').between(query_res.profit_min, query_res.profit_max))
        elif query_res.profit_min is not None:
            where_conditions.append(col('net_income_ttm') >= query_res.profit_min)

        if where_conditions:
            q = q.where(*where_conditions)

        q = q.order_by('total_revenue_ttm', ascending=False).limit(limit)
        count, df = q.get_scanner_data()
        df = df.loc[:, ~df.columns.duplicated()]

        print(f"📊 [{get_now_str()}] [Raw Screener Output]: Retrieved {count} total matching symbols.")

        _emit("search_query", {
            "query_str": f"sector={query_res.sector} market={market} limit={limit}",
            "source": "tradingview",
            "result_count": count,
        })

        # Fallback Level 1
        if df.empty and query_res.industry:
            print("⚠️ [Fallback]: Retrying with Sector-level filter...")
            _emit("progress", {"stage": "screener_fetch", "progress_pct": 18, "message": "Fallback: sector-only filter"})
            fb_where = []
            if query_res.sector:
                fb_where.append(col('sector') == query_res.sector)
            if query_res.revenue_min is not None and query_res.revenue_max is not None:
                fb_where.append(col('total_revenue_ttm').between(query_res.revenue_min, query_res.revenue_max))
            elif query_res.revenue_min is not None:
                fb_where.append(col('total_revenue_ttm') >= query_res.revenue_min)
            elif query_res.revenue_max is not None:
                fb_where.append(col('total_revenue_ttm') <= query_res.revenue_max)
            q_fallback = Query().set_markets(market).select('name', 'sector', 'industry', 'total_revenue_ttm', 'net_income_ttm')
            if fb_where:
                q_fallback = q_fallback.where(*fb_where)
            count, df = q_fallback.order_by('total_revenue_ttm', ascending=False).limit(limit).get_scanner_data()
            df = df.loc[:, ~df.columns.duplicated()]

        # Fallback Level 2
        if df.empty:
            print("⚠️ [Fallback]: Retrying with relaxed financial constraints...")
            _emit("progress", {"stage": "screener_fetch", "progress_pct": 19, "message": "Fallback: relaxed revenue filter"})
            q_fallback = Query().set_markets(market).select('name', 'sector', 'industry', 'total_revenue_ttm', 'net_income_ttm')
            fb_where = []
            if query_res.sector:
                fb_where.append(col('sector') == query_res.sector)
            if query_res.revenue_min is not None:
                fb_where.append(col('total_revenue_ttm') >= (query_res.revenue_min * 0.5))
            if fb_where:
                q_fallback = q_fallback.where(*fb_where)
            count, df = q_fallback.order_by('total_revenue_ttm', ascending=False).limit(limit).get_scanner_data()
            df = df.loc[:, ~df.columns.duplicated()]

        # Deduplicate
        initial_len = len(df)
        if 'name' in df.columns:
            df = df.drop_duplicates(subset='name', keep='first')
        dedup_len = len(df)
        print(f"✂️  [{get_now_str()}] [Deduplication]: Removed {initial_len - dedup_len} duplicates, retaining {dedup_len} unique companies.")

        raw_list = df.to_dict(orient='records')

        _emit("node_exit", {
            "node_name": "screener_fetch",
            "step_num": 2,
            "duration_ms": int((time.time() - t0) * 1000),
            "output_summary": {
                "raw_count": len(raw_list),
                "screened_count": count,
                "dedup_removed": initial_len - dedup_len,
                "sample_tickers": [r.get("ticker") or r.get("name") for r in raw_list[:5]],
            },
        })
        _emit("progress", {
            "stage": "screener_fetch",
            "progress_pct": 25,
            "count": len(raw_list),
            "message": f"Screened {count} symbols → {len(raw_list)} candidates",
        })

        return Command(
            goto="yfinance_enricher",
            update={"raw_companies": raw_list}
        )

    except Exception as e:
        import traceback
        _emit("node_exit", {
            "node_name": "screener_fetch",
            "step_num": 2,
            "duration_ms": int((time.time() - t0) * 1000),
            "error": str(e),
        }, level="error")
        print(f"❌ [{get_now_str()}] [ERROR in screener_fetch]: {e}")
        traceback.print_exc()
        raise e


# ─────────────────────────────────────────────────────────────────────────────
# Node 3 helper: per-company enrichment
# ─────────────────────────────────────────────────────────────────────────────

async def enrich_single_company(company: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        raw_ticker = company.get('ticker')
        ticker_str = str(raw_ticker) if raw_ticker is not None and str(raw_ticker).lower() != 'nan' else ""
        yahoo_ticker, symbol, suffix = convert_ticker(ticker_str)

        city = None
        state_val = None
        country = None
        source_used = "yfinance"
        emp_count = None
        bus_summary = None
        website = None
        full_name = None

        if yahoo_ticker:
            try:
                def fetch_yf():
                    return yf.Ticker(yahoo_ticker).info

                info = await asyncio.to_thread(fetch_yf)

                if isinstance(info, dict):
                    emp_count = info.get("fullTimeEmployees")
                    bus_summary = info.get("longBusinessSummary")
                    website = info.get("website")
                    full_name = info.get("longName") or info.get("longname") or info.get("shortName")
                    city = info.get("city")
                    state_val = info.get("state")
                    country = info.get("country")
            except Exception:
                pass

        if ticker_str and (not website or str(website).strip().lower() in ("not found", "none", "", "nan")):
            fb_site = fallback_financedatabase_website(ticker_str)
            if fb_site:
                website = fb_site
                source_used = "financedatabase fallback"
            else:
                website = "NOT FOUND"
        elif not website:
            website = "NOT FOUND"

        comp_name = full_name if (full_name and str(full_name).strip()) else company.get("name", "")
        loc_parts = [str(v).strip() for v in [city, state_val, country] if v and str(v).strip()]
        yf_location = ", ".join(loc_parts) if loc_parts else None

        enriched_record = {
            "ticker": ticker_str,
            "name": comp_name,
            "industry": company.get("industry", "") or company.get("sector", ""),
            "revenue_ttm": company.get("total_revenue_ttm"),
            "net_income_ttm": company.get("net_income_ttm"),
            "employee_count": emp_count,
            "business_summary": bus_summary,
            "website": website,
            "city": city,
            "state": state_val,
            "country": country,
            "location": yf_location,
            "enrichment_source": source_used,
            "linkedin_guessed": None,
            "linkedin_verified": None,
            "linkedin_confirmed": False,
        }

        # Emit granular company_enriched event for visualizer EnrichScene
        _emit("company_enriched", {
            "ticker": ticker_str,
            "name": comp_name,
            "industry": enriched_record["industry"],
            "revenue_ttm": enriched_record["revenue_ttm"],
            "employee_count": emp_count,
            "website": website,
            "city": city,
            "country": country,
            "source": source_used,
        })

        return enriched_record


# ─────────────────────────────────────────────────────────────────────────────
# Node 3: YFinance Enricher
# ─────────────────────────────────────────────────────────────────────────────

async def yfinance_enricher(state: ShortlisterState, config: RunnableConfig) -> Command[Literal["cleaner"]]:
    t0 = time.time()
    _emit("node_enter", {
        "node_name": "yfinance_enricher",
        "step_num": 3,
        "description": "Fetching website, headcount & business summary via yfinance with financedatabase fallback",
        "state_keys_present": list(state.keys()),
    })

    raw_companies = state.get("raw_companies", [])

    _emit("progress", {
        "stage": "yfinance_enricher",
        "progress_pct": 30,
        "count": len(raw_companies),
        "message": f"Enriching {len(raw_companies)} companies via yfinance...",
    })

    print(f"🔄 [{get_now_str()}] [Concurrent Enrichment]: Processing {len(raw_companies)} companies (max concurrency: 5)...")

    sem = asyncio.Semaphore(5)
    tasks = [enrich_single_company(c, sem) for c in raw_companies]
    enriched = await asyncio.gather(*tasks)

    found_count = sum(1 for c in enriched if c.get("website") != "NOT FOUND")
    missing_count = len(enriched) - found_count

    print(f"\n🌐 [{get_now_str()}] [Enrichment Results]:")
    print(f"   ├─ Total Processed:         {len(enriched)}")
    print(f"   ├─ Valid Websites Found:    {found_count}")
    print(f"   └─ Missing Websites:        {missing_count}")

    _emit("node_exit", {
        "node_name": "yfinance_enricher",
        "step_num": 3,
        "duration_ms": int((time.time() - t0) * 1000),
        "output_summary": {
            "total_enriched": len(enriched),
            "websites_found": found_count,
            "websites_missing": missing_count,
        },
    })
    _emit("progress", {
        "stage": "yfinance_enricher",
        "progress_pct": 42,
        "count": found_count,
        "message": f"Enriched {len(enriched)} companies — {found_count} with websites",
    })

    return Command(
        goto="cleaner",
        update={"enriched_companies": list(enriched)}
    )


# ─────────────────────────────────────────────────────────────────────────────
# Node 4: Cleaner
# ─────────────────────────────────────────────────────────────────────────────

async def cleaner(state: ShortlisterState, config: RunnableConfig) -> Command[Literal["linkedin_verifier"]]:
    t0 = time.time()
    _emit("node_enter", {
        "node_name": "cleaner",
        "step_num": 4,
        "description": "Filtering out NOT FOUND websites and selecting top companies by revenue",
        "state_keys_present": list(state.keys()),
    })

    configurable = Configuration.from_runnable_config(config)
    enriched = state.get("enriched_companies", [])
    initial_count = len(enriched)

    _emit("progress", {
        "stage": "cleaner",
        "progress_pct": 45,
        "count": initial_count,
        "message": f"Cleaning {initial_count} enriched companies...",
    })

    cleaned = [
        c for c in enriched
        if c.get("website") and str(c.get("website")).strip().upper() not in ("NOT FOUND", "NONE", "NAN", "")
    ]
    removed_count = initial_count - len(cleaned)

    print(f"🧹 [{get_now_str()}] [Filter Step]: Filtered out {removed_count} companies with unresolvable website fields.")

    # Emit company_dropped events for the CleanScene visualizer
    for c in enriched:
        if c.get("website") and str(c.get("website")).strip().upper() in ("NOT FOUND", "NONE", "NAN", ""):
            _emit("company_dropped", {
                "company_name": c.get("name", ""),
                "reason": "missing website",
            })

    # Sort by revenue descending
    cleaned.sort(key=lambda x: (x.get("revenue_ttm") or 0), reverse=True)
    top_n = cleaned[:configurable.top_n_companies]

    print(f"⭐ [{get_now_str()}] [Shortlisting]: Selected Top {len(top_n)} companies by revenue.")
    print(f"\n🏆 [Top Shortlisted Candidates]:")
    for rank, comp in enumerate(top_n, 1):
        rev = f"{comp.get('revenue_ttm', 0):,.0f}" if comp.get('revenue_ttm') else "N/A"
        print(f"   #{rank:02d} {comp.get('name'):<30} | Revenue: {rev:<18} | Website: {comp.get('website')}")

    _emit("node_exit", {
        "node_name": "cleaner",
        "step_num": 4,
        "duration_ms": int((time.time() - t0) * 1000),
        "output_summary": {
            "initial_count": initial_count,
            "removed_count": removed_count,
            "shortlisted_count": len(top_n),
            "top_companies": [{"name": c.get("name"), "revenue_ttm": c.get("revenue_ttm")} for c in top_n],
        },
    })
    _emit("progress", {
        "stage": "cleaner",
        "progress_pct": 50,
        "count": len(top_n),
        "message": f"Shortlisted {len(top_n)} companies for parallel LinkedIn research",
    })

    return Command(
        goto="linkedin_verifier",
        update={"cleaned_companies": top_n}
    )


# ─────────────────────────────────────────────────────────────────────────────
# Node 5: LinkedIn Verifier (parallel per-company)
# ─────────────────────────────────────────────────────────────────────────────

async def _search_company_linkedin_impl(comp: dict, config: RunnableConfig, sem: asyncio.Semaphore, target_location: str) -> dict:
    async with sem:
        comp_name = comp.get("name", "") or "Unknown Company"
        comp_web = comp.get("website", "")
        comp_desc = comp.get("business_summary") or "N/A"
        session_id = config.get("configurable", {}).get("thread_id", "session")

        safe_comp = re.sub(r'[^a-zA-Z0-9]', '', comp_name)[:15] or "company"
        comp_session_id = f"{session_id}-{safe_comp}"

        async def _task_find_company_linkedin():
            comp_copy = dict(comp)
            found_url = "NOT FOUND"
            is_confirmed = False

            if comp_web and str(comp_web).strip().lower() not in ("not found", "none", "nan", ""):
                try:
                    from selenium_extractor import extract_linkedin_from_website_selenium
                    found_selenium_url = await asyncio.to_thread(extract_linkedin_from_website_selenium, comp_web, company_name=comp_name)
                    if found_selenium_url:
                        comp_copy["linkedin_verified"] = found_selenium_url
                        comp_copy["linkedin_confirmed"] = True
                        _emit("contact_found", {
                            "company_name": comp_name,
                            "linkedin_url": found_selenium_url,
                            "source": "selenium",
                            "confirmed": True,
                        })
                        print(f"   [{get_now_str()}] [Company: {comp_name}] 🎯 [Selenium]: ➔ {found_selenium_url} [CONFIRMED ✅]", flush=True)
                        return comp_copy
                except Exception as sel_err:
                    print(f"   [{get_now_str()}] [Company: {comp_name}] ⚠️ [Selenium Warning]: {sel_err}", flush=True)

            _emit("search_query", {
                "query_str": f'"{comp_name}" "{comp_web}" site:linkedin.com/company',
                "source": "linkedin_research",
                "company": comp_name,
            })
            print(f"   [{get_now_str()}] [Company: {comp_name}] 🔄 [Fallback]: Launching LLM Search Sub-Agent...", flush=True)

            prompt_content = (
                f"Search Official LinkedIn for Candidate Company (1 Company Per Run):\n"
                f"- Company Name: {comp_name}\n"
                f"- Official Website: {comp_web}\n"
                f"- Company Description: {comp_desc}\n\n"
                f"Instructions: PRIORITIZE BATCH SEARCH QUERIES! Perform web search using structured batch queries combining Company Name, Website domain, and site filter: '\"{comp_name}\" \"{comp_web}\" site:linkedin.com/company'.\n"
                f"Extract the exact official LinkedIn company URL from search results.\n"
                f"Output Format:\n"
                f"Company Name: {comp_name}\n"
                f"Official Website: {comp_web}\n"
                f"Verified LinkedIn URL: <exact URL or NOT FOUND>\n"
                f"LinkedIn Confirmed: Yes/No"
            )

            try:
                res = await researcher_subgraph.ainvoke({
                    "researcher_messages": [HumanMessage(content=prompt_content)],
                    "research_topic": prompt_content
                }, config)

                output_text = res.get("compressed_research", "") or ""
                notes = res.get("raw_notes", []) or []
                combined = output_text + "\n" + "\n".join([str(n) for n in notes])

                urls = re.findall(r'https?://(?:www\.)?linkedin\.com/company/[a-zA-Z0-9\-_%]+', combined, re.IGNORECASE)
                if urls:
                    found_url = urls[0].rstrip('./,;')
                    if "confirmed: no" not in combined.lower() and "unverified" not in combined.lower() and "not found" not in combined.lower():
                        is_confirmed = True
                elif "confirmed: yes" in combined.lower() or "verified linkedin" in combined.lower():
                    is_confirmed = True

                comp_copy["linkedin_verified"] = found_url
                comp_copy["linkedin_confirmed"] = is_confirmed

                if found_url != "NOT FOUND":
                    _emit("contact_found", {
                        "company_name": comp_name,
                        "linkedin_url": found_url,
                        "source": "llm_researcher",
                        "confirmed": is_confirmed,
                    })

                status = "CONFIRMED ✅" if is_confirmed else "NOT FOUND ⚠️"
                print(f"   [{get_now_str()}] [Company: {comp_name}] [Agent Loop Response]: ➔ {found_url} [{status}]", flush=True)
                return comp_copy
            except Exception as e:
                print(f"   [{get_now_str()}] [Company: {comp_name}] [Agent Loop Error]: {e}", flush=True)
                comp_copy["linkedin_verified"] = "NOT FOUND"
                comp_copy["linkedin_confirmed"] = False
                return comp_copy

        async def task_find_company_linkedin():
            from logging_utils.context import bind_log_context
            from logging_utils.lifecycle import subagent_lifecycle

            execution_id = f"{comp_session_id}:company-linkedin-verifier"
            with bind_log_context(
                agent="shortlister",
                run_id=session_id,
                parent_run_id=session_id,
                execution_id=execution_id,
                parent_execution_id=comp_session_id,
                company=comp_name,
                branch="company_linkedin_verifier",
            ):
                with subagent_lifecycle(
                    company=comp_name,
                    execution_id=execution_id,
                    parent_execution_id=comp_session_id,
                    branch="company_linkedin_verifier",
                    component="graph.shortlister",
                ):
                    return await _task_find_company_linkedin()

        async def task_run_finder_subgraph():
            print(
                f"   [{get_now_str()}] [Company: {comp_name}] 🚀 [LinkedIn Finder Subgraph]: "
                f"Launching in-process subgraph (Location: {target_location}, Session: {comp_session_id})...",
                flush=True,
            )
            _emit("progress", {
                "stage": "linkedin_verifier",
                "message": f"Searching contacts for {comp_name}",
                "company": comp_name,
            })
            return await run_linkedin_finder_subgraph(
                company_name=comp_name,
                company_website=comp_web,
                company_linkedin="",
                location=target_location,
                session_id=comp_session_id,
                parent_session_id=session_id,
            )

        task_1 = asyncio.create_task(task_find_company_linkedin())
        task_2 = asyncio.create_task(task_run_finder_subgraph())
        comp_res, dms = await asyncio.gather(task_1, task_2)

        # Emit contact_found for each discovered decision maker
        for dm in (dms or []):
            _emit("contact_found", {
                "person_name": dm.get("name"),
                "role": dm.get("position"),
                "company": comp_name,
                "linkedin_url": dm.get("linkedin_url"),
                "email_found": dm.get("email"),
            })

        comp_res["decision_makers"] = dms or []
        comp_res["location"] = comp_res.get("location") or target_location
        return comp_res


async def search_company_linkedin(comp: dict, config: RunnableConfig, sem: asyncio.Semaphore, target_location: str) -> dict:
    """Run one company with authoritative root lifecycle and contact telemetry."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from logging_utils.context import bind_log_context
    from logging_utils.lifecycle import subagent_lifecycle
    from logging_utils.registry import emit_event
    from logging_utils.snapshots import sanitize_decision_makers

    comp_name = comp.get("name", "") or "Unknown Company"
    session_id = config.get("configurable", {}).get("thread_id", "session")
    safe_comp = re.sub(r"[^a-zA-Z0-9]", "", comp_name)[:15] or "company"
    comp_session_id = f"{session_id}-{safe_comp}"

    with bind_log_context(
        agent="shortlister",
        run_id=session_id,
        parent_run_id=session_id,
        execution_id=comp_session_id,
        parent_execution_id=session_id,
        company=comp_name,
        branch="company_research",
    ):
        with subagent_lifecycle(
            company=comp_name,
            execution_id=comp_session_id,
            parent_execution_id=session_id,
            branch="company_research",
            component="graph.shortlister",
        ) as terminal_data:
            result = await _search_company_linkedin_impl(comp, config, sem, target_location)
            decision_makers = result.get("decision_makers") or []
            contacts = sanitize_decision_makers(decision_makers)
            terminal_data["contact_count"] = len(contacts)
            emit_event(
                "company_contacts_snapshot",
                {
                    "company": comp_name,
                    "execution_id": comp_session_id,
                    "contact_count": len(contacts),
                    "contacts": contacts,
                },
                component="graph.shortlister",
            )
            return result


async def linkedin_verifier(state: ShortlisterState, config: RunnableConfig) -> Command[Literal["excel_exporter_node"]]:
    t0 = time.time()
    _emit("node_enter", {
        "node_name": "linkedin_verifier",
        "step_num": 5,
        "description": "Parallel LinkedIn verification + contact finder subgraph per company",
        "state_keys_present": list(state.keys()),
    })

    cleaned_companies = state.get("cleaned_companies", [])
    configurable = Configuration.from_runnable_config(config)
    query_info = state.get("screener_query")
    target_location = query_info.location if query_info and hasattr(query_info, "location") and query_info.location else "India"

    print(f"🤖 [{get_now_str()}] [Agent Loop Start]: Processing {len(cleaned_companies)} companies in parallel...")
    print(f"   Target Location: {target_location}")
    print("   Directive: LinkedIn Verification Subgraph AND LinkedIn Finder Agent in parallel\n", flush=True)

    _emit("progress", {
        "stage": "linkedin_verifier",
        "progress_pct": 52,
        "count": 0,
        "message": f"Starting parallel research for {len(cleaned_companies)} companies",
    })

    sem = asyncio.Semaphore(configurable.max_concurrent_research_units)
    tasks = [search_company_linkedin(c, config, sem, target_location) for c in cleaned_companies]
    verified_companies = await asyncio.gather(*tasks)

    total_contacts = sum(len(c.get("decision_makers") or []) for c in verified_companies)
    confirmed_count = sum(1 for c in verified_companies if c.get("linkedin_confirmed"))

    print(f"\n🔍 [{get_now_str()}] [Final Parallel Agent Loop Results Summary]:", flush=True)
    for idx, comp in enumerate(verified_companies, 1):
        status = "CONFIRMED ✅" if comp.get("linkedin_confirmed") else "UNVERIFIED ⚠️"
        print(f"   {idx:02d}. {comp.get('name'):<28} | LinkedIn: {comp.get('linkedin_verified')} [{status}]", flush=True)

    _emit("node_exit", {
        "node_name": "linkedin_verifier",
        "step_num": 5,
        "duration_ms": int((time.time() - t0) * 1000),
        "output_summary": {
            "companies_processed": len(verified_companies),
            "linkedin_confirmed": confirmed_count,
            "total_contacts_found": total_contacts,
        },
    })
    _emit("progress", {
        "stage": "linkedin_verifier",
        "progress_pct": 90,
        "count": total_contacts,
        "message": f"Research complete — {total_contacts} contacts across {len(verified_companies)} companies",
    })

    return Command(
        goto="excel_exporter_node",
        update={"verified_companies": list(verified_companies)}
    )


# ─────────────────────────────────────────────────────────────────────────────
# Node 6: Excel Exporter
# ─────────────────────────────────────────────────────────────────────────────

async def excel_exporter_node(state: ShortlisterState, config: RunnableConfig) -> Command[Literal["__end__"]]:
    t0 = time.time()
    _emit("node_enter", {
        "node_name": "excel_exporter_node",
        "step_num": 6,
        "description": "Compiling verified company data into styled Excel spreadsheet & JSON log",
        "state_keys_present": list(state.keys()),
    })

    verified_companies = state.get("verified_companies", [])
    query_info = state.get("screener_query")
    query_dict = query_info.dict() if hasattr(query_info, "dict") else {}
    session_id = config.get("configurable", {}).get("thread_id", "session")

    _emit("progress", {
        "stage": "excel_exporter_node",
        "progress_pct": 93,
        "message": "Assembling final report...",
    })

    save_res = save_all(verified_companies, screener_query=query_dict, session_id=session_id)
    excel_path = save_res.get('excel', '')

    print(f"\n📁 [{get_now_str()}] [Export Summary]:")
    print(f"   ├─ Excel Workbook Saved: {excel_path}")
    print(f"   ├─ JSON Snapshot Saved:  {save_res.get('json')}")
    print(f"   └─ Total Verified Companies Exported: {len(verified_companies)}")

    total_contacts = sum(len(c.get("decision_makers") or []) for c in verified_companies)

    _emit("node_exit", {
        "node_name": "excel_exporter_node",
        "step_num": 6,
        "duration_ms": int((time.time() - t0) * 1000),
        "output_summary": {
            "excel_path": excel_path,
            "json_path": save_res.get('json'),
            "company_count": len(verified_companies),
            "contact_count": total_contacts,
            "report_filename": os.path.basename(excel_path) if excel_path else "",
        },
    })
    _emit("progress", {
        "stage": "excel_exporter_node",
        "progress_pct": 100,
        "count": total_contacts,
        "message": f"Report ready — {len(verified_companies)} companies, {total_contacts} contacts",
    })

    return Command(goto=END)


# ─────────────────────────────────────────────────────────────────────────────
# Graph construction
# ─────────────────────────────────────────────────────────────────────────────

shortlister_builder = StateGraph(ShortlisterState, context_schema=Configuration)

shortlister_builder.add_node("query_formulator", query_formulator)
shortlister_builder.add_node("screener_fetch", screener_fetch)
shortlister_builder.add_node("yfinance_enricher", yfinance_enricher)
shortlister_builder.add_node("cleaner", cleaner)
shortlister_builder.add_node("linkedin_verifier", linkedin_verifier)
shortlister_builder.add_node("excel_exporter_node", excel_exporter_node)

shortlister_builder.add_edge(START, "query_formulator")

shortlister_agent = shortlister_builder.compile()
