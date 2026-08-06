import asyncio
import os
import sys
import time
from datetime import datetime

import config
from configuration import Configuration
from logging_ import PipelineLogger, log_print, set_logger
from graph.builder import build_graph


def _bootstrap_logger(session_id: str):
    """Wire up the shared logging_utils logger for this process."""
    _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)
    from logging_utils.config import setup_logging
    logger = setup_logging(agent="linkedin", run_id=session_id)
    set_logger(logger)
    return logger

async def main():
    session_id = f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_start = time.time()
    logger = _bootstrap_logger(session_id)

    log_print("==================================================")
    log_print("        Welcome to Contact Finder Agent           ")
    log_print("==================================================")
    
    import argparse
    parser = argparse.ArgumentParser(description="Contact Finder Agent")
    parser.add_argument("--company_name", type=str, default="", help="Company Name")
    parser.add_argument("--company_linkedin", type=str, default="", help="Company LinkedIn URL")
    parser.add_argument("--company_website", type=str, default="", help="Company Website URL")
    parser.add_argument("--location", type=str, default="India", help="Target Location")
    parser.add_argument("--session_id", type=str, default="", help="Session ID")
    
    args, _ = parser.parse_known_args()

    if args.company_name.strip():
        company_name = args.company_name.strip()
        company_linkedin = args.company_linkedin.strip()
        company_website = args.company_website.strip()
        company_location = args.location.strip() or "India"
        session_id = args.session_id.strip() if args.session_id.strip() else session_id
    else:
        company_name = input("Enter Company Name:\n> ").strip()
        if not company_name:
            log_print("Company Name cannot be empty. Exiting.")
            return

        company_linkedin = input("Enter Company LinkedIn URL:\n> ").strip()
        company_website = input("Enter Company Website URL:\n> ").strip()
        company_location = input("Enter Company Location (e.g., City, Country):\n> ").strip()

    if not company_name:
        log_print("Company Name cannot be empty. Exiting.")
        return

    logger.event("pipeline_start", {
        "company_name": company_name,
        "company_website": company_website,
        "location": company_location,
        "session_id": session_id,
    }, component="main")
    pipeline_logger = PipelineLogger(session_id=session_id)

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    log_print(f"\n🚀 Starting pipeline for '{company_name}' [Session: {session_id}]...")

    initial_state = {
        "company_name": company_name,
        "company_linkedin": company_linkedin,
        "company_website": company_website,
        "location": company_location,
        "generated_query": "",
        "serp_raw_response": {},
        "ai_overview": "",
        "decision_makers": [],
        "scrape_calls_used": 0,
        "loop_memory": [],
        "session_id": session_id
    }

    try:
        from langgraph.checkpoint.memory import MemorySaver
        saver = MemorySaver()
        log_print("Building agent graph with in-memory checkpointer...")
        graph = build_graph(checkpointer=saver)
            
        runnable_config = {
            "configurable": {
                "thread_id": session_id,
            },
            "callbacks": [pipeline_logger]
        }
        
        result = await graph.ainvoke(
            initial_state,
            config=runnable_config
        )

        log_print("\n==================================================")
        log_print("🎉 Pipeline finished successfully!")
        log_print("==================================================")

        dms = result.get("decision_makers", [])
        usage = pipeline_logger.get_token_usage_summary()
        duration_ms = int((time.time() - run_start) * 1000)

        logger.event("pipeline_end", {
            "company_name": company_name,
            "decision_makers_count": len(dms),
            "total_tokens": usage["total_tokens"],
            "total_cost": usage["total_cost"],
            "duration_ms": duration_ms,
        }, component="main")

        log_print(f"\n✅ Extracted {len(dms)} decision makers for {company_name}:")
        for idx, dm in enumerate(dms, 1):
            log_print(f"  {idx}. {dm.get('name')} ({dm.get('position')}) -> {dm.get('linkedin_url')}")

        log_print(f"\n📊 Output Excel: output/contacts_{session_id}.xlsx")
        log_print(f"💾 State JSON: output/agent_state_{session_id}.json")
        log_print(f"📋 Event Log: {pipeline_logger.log_store.log_file}")

        log_print(f"\n📈 Token Usage & Cost:")
        log_print(f"   Input Tokens:  {usage['total_prompt_tokens']} (${usage['cost_input']:.6f})")
        log_print(f"   Output Tokens: {usage['total_completion_tokens']} (${usage['cost_output']:.6f})")
        log_print(f"   Total Tokens:  {usage['total_tokens']}")
        log_print(f"   Total Cost:    ${usage['total_cost']:.6f}")

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.event("pipeline_error", {"error": str(e), "traceback": tb, "company_name": company_name}, component="main")
        log_print(f"\n❌ An error occurred during execution: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    os.makedirs(config.LOG_DIR, exist_ok=True)
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(main())
