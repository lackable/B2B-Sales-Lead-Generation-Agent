"""
Bridge module: runs the LinkedIn Finder agent as a native in-process LangGraph
subgraph for the Shortlister agent's Node 5 (linkedin_verifier).

Design notes
------------
- The Finder agent is a plain import — the previous ``sys.modules`` stash/swap and
  ``sys.path`` juggling are gone, because both agents now live inside the single
  ``leadgen`` package.
- The compiled graph is cached for the process lifetime; each company run gets its
  own ``thread_id``, so parallel runs cannot cross-contaminate state.
- Per-company Excel + JSON files are still written by the Finder agent's output_node.
- decision_makers are returned directly from ainvoke().
"""

from typing import Optional

from leadgen.agents.linkedin_finder.graph import contact_finder_builder
from leadgen.core.telemetry.context import bind_log_context
from leadgen.core.telemetry.lifecycle import subagent_lifecycle

_cached_contact_finder = None


def _get_contact_finder():
    """
    Compile the Finder graph once per process.

    Matches the previous in-process behaviour: no checkpointer is attached, so
    each run is isolated by its own configurable thread_id.
    """
    global _cached_contact_finder
    if _cached_contact_finder is None:
        _cached_contact_finder = contact_finder_builder.compile()
    return _cached_contact_finder


async def _run_linkedin_finder_subgraph_impl(
    company_name: str,
    company_website: str,
    company_linkedin: str,
    location: str,
    session_id: str,
) -> list[dict]:
    """
    Invoke the LinkedIn Finder Agent graph in-process for a single company and
    return the discovered decision_makers list.
    """
    graph = _get_contact_finder()

    initial_state = {
        "company_name": company_name,
        "company_linkedin": company_linkedin or "",
        "company_website": company_website or "",
        "location": location or "India",
        "generated_query": "",
        "serp_raw_response": {},
        "ai_overview": "",
        "decision_makers": [],
        "scrape_calls_used": 0,
        "loop_memory": [],
        "session_id": session_id,
    }

    subgraph_config = {
        "configurable": {
            "thread_id": session_id,
        },
    }

    try:
        result = await graph.ainvoke(initial_state, config=subgraph_config)

        decision_makers = result.get("decision_makers", []) or []
        print(
            f"   [{session_id}] [Company: {company_name}] ✅ [LinkedIn Finder Subgraph]: Completed — "
            f"found {len(decision_makers)} decision maker(s).",
            flush=True,
        )
        return decision_makers
    except Exception as exc:
        import traceback
        print(
            f"   [{session_id}] [Company: {company_name}] ❌ [LinkedIn Finder Subgraph Error]: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        traceback.print_exc()
        return []


async def run_linkedin_finder_subgraph(
    company_name: str,
    company_website: str,
    company_linkedin: str,
    location: str,
    session_id: str,
    parent_session_id: Optional[str] = None,
) -> list[dict]:
    """Run the finder graph inside a correlated child logging context."""
    parent_run_id = parent_session_id or session_id
    execution_id = f"{session_id}:contact-finder"

    with bind_log_context(
        agent="linkedin",
        run_id=session_id,
        parent_run_id=parent_run_id,
        execution_id=execution_id,
        parent_execution_id=session_id,
        company=company_name,
        branch="linkedin_contact_finder",
    ):
        with subagent_lifecycle(
            company=company_name,
            execution_id=execution_id,
            parent_execution_id=session_id,
            branch="linkedin_contact_finder",
            component="agents.shortlister.subgraphs.linkedin_finder",
        ) as terminal_data:
            decision_makers = await _run_linkedin_finder_subgraph_impl(
                company_name=company_name,
                company_website=company_website,
                company_linkedin=company_linkedin,
                location=location,
                session_id=session_id,
            )
            terminal_data["contact_count"] = len(decision_makers)
            return decision_makers
