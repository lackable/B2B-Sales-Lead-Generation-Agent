"""CLI entry point for the Shortlister agent.

Usage::

    python -m leadgen.agents.shortlister "Indian specialty chemical companies with revenue above 500 Cr"

With no query argument the agent prompts interactively. The API orchestrator
launches this module as a subprocess and injects ``PIPELINE_RUN_ID``.
"""

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime

from leadgen import config
from leadgen.agents.shortlister.configuration import Configuration  # noqa: F401  (re-exported for parity)
from leadgen.agents.shortlister.graph import build_graph
from leadgen.core.telemetry import PipelineLogger
from leadgen.core.telemetry.log_store import set_logger
from leadgen.core.telemetry.adapter import setup_logging
from langchain_core.messages import HumanMessage


def _bootstrap_logger(session_id: str):
    """Wire up the shared structured logger so every module can emit events from the start."""
    logger = setup_logging(agent="shortlister", run_id=session_id)
    set_logger(logger)
    return logger


async def main():
    parser = argparse.ArgumentParser(description="Shortlister Agent")
    parser.add_argument(
        "query",
        nargs="*",
        help="Natural-language company profile to shortlist (prompted interactively if omitted)",
    )
    args = parser.parse_args()

    session_id = os.getenv("PIPELINE_RUN_ID") or f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_start = time.time()

    # ── Structured logger must be first ───────────────────────────────────────
    logger = _bootstrap_logger(session_id)

    if args.query:
        user_input = " ".join(args.query)
    else:
        user_input = input("Describe the company profile you are looking for:\n> ")

    if not user_input.strip():
        logger.event("pipeline_error", {"error": "Empty input. Exiting."}, component="main")
        print("❌ Empty input. Exiting.")
        return

    logger.event("pipeline_start", {
        "user_query": user_input,
        "session_id": session_id,
        "pipeline_mode": "6-Step Parallel Agent Loop (TradingView + yfinance + Parallel LinkedIn Search Loop)",
    }, component="main")

    print("\n" + "=" * 80)
    print("🚀 SHORTLISTER AGENT PIPELINE — MULTI-STEP EXECUTION")
    print("=" * 80)
    print(f"\n📋 Session ID: {session_id}")
    print(f"📝 Target Query: \"{user_input}\"")
    print("⚡ Pipeline Mode: 6-Step Parallel Agent Loop (TradingView + yfinance + Parallel LinkedIn Search Loop)")

    pipeline_logger = PipelineLogger(session_id=session_id)

    initial_state = {
        "messages": [HumanMessage(content=user_input)]
    }

    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        async with AsyncSqliteSaver.from_conn_string(config.MEMORY_DB_PATH) as saver:
            graph = build_graph(checkpointer=saver)

            runnable_config = {
                "configurable": {
                    "thread_id": session_id,
                    "screener_market": config.SCREENER_MARKET,
                    "screener_limit": config.SCREENER_LIMIT,
                    "top_n_companies": config.TOP_N_COMPANIES,
                },
                "callbacks": [pipeline_logger],
            }

            result = await graph.ainvoke(initial_state, config=runnable_config)

        print("\n" + "=" * 80)
        print("🎉 SHORTLISTER PIPELINE COMPLETED SUCCESSFULLY!")
        print("=" * 80)

        verified_companies = result.get("verified_companies", [])
        usage = pipeline_logger.get_token_usage_summary()
        duration_ms = int((time.time() - run_start) * 1000)

        # ── Emit pipeline_end structured event ─────────────────────────────────
        logger.event("pipeline_end", {
            "total_tokens": usage["total_tokens"],
            "total_cost": usage["total_cost"],
            "cost_input": usage["cost_input"],
            "cost_output": usage["cost_output"],
            "total_prompt_tokens": usage["total_prompt_tokens"],
            "total_completion_tokens": usage["total_completion_tokens"],
            "duration_ms": duration_ms,
            "company_count": len(verified_companies),
            "report_filename": pipeline_logger.log_store.log_file,
        }, component="main")

        print(f"\n🏆 FINAL SHORTLIST SUMMARY ({len(verified_companies)} Companies):")
        print("-" * 80)
        for idx, comp in enumerate(verified_companies, 1):
            name = comp.get('name') or comp.get('company_name')
            ticker = comp.get('ticker')
            rev = f"{comp.get('revenue_ttm', 0):,.0f}" if comp.get('revenue_ttm') else "N/A"
            web = comp.get('website')
            li = comp.get('linkedin_verified')
            conf = "Confirmed ✅" if comp.get('linkedin_confirmed') else "Unverified ⚠️"
            print(f" {idx:02d}. {name:<28} ({ticker:<8}) | Rev: {rev:<16} | Web: {web:<30} | LinkedIn: {li} [{conf}]")

        print("\n" + "-" * 80)
        print("📊 METRICS & COST SUMMARY:")
        print(f"   ├─ Prompt Tokens:      {usage['total_prompt_tokens']:,} (${usage['cost_input']:.6f})")
        print(f"   ├─ Completion Tokens:  {usage['total_completion_tokens']:,} (${usage['cost_output']:.6f})")
        print(f"   ├─ Total Tokens Used:  {usage['total_tokens']:,}")
        print(f"   ├─ Total API Cost:     ${usage['total_cost']:.6f}")
        print(f"   └─ Event Log File:     {pipeline_logger.log_store.log_file}")
        print("=" * 80 + "\n")

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.event("pipeline_error", {"error": str(e), "traceback": tb}, component="main")
        print(f"\n❌ An error occurred during execution: {e}")
        traceback.print_exc()


def run() -> None:
    """Sync entry point used by ``python -m leadgen.agents.shortlister``."""
    config.ensure_runtime_dirs()

    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())


if __name__ == "__main__":
    run()
