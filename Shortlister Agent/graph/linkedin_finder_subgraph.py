"""
Bridge module: imports the LinkedIn Finder Agent as a native in-process
LangGraph subgraph and exposes run_linkedin_finder_subgraph() for use
inside Shortlister Agent's Node 5 (linkedin_verifier).

Design notes
------------
- Stashes Shortlister Agent's clashing modules (graph, config, etc.) during
  the dynamic import of LinkedIn Finder Agent's contact_finder graph to prevent
  Python module namespace collisions.
- Each company run gets its own MemorySaver checkpointer so there is no
  state cross-contamination between parallel runs.
- Per-company Excel + JSON output files are still written by the Finder
  Agent's output_node.
- decision_makers are returned directly from ainvoke().
"""

import os
import sys
import contextlib

_cached_contact_finder = None

@contextlib.contextmanager
def isolated_finder_context():
    """
    Context manager that temporarily isolates sys.modules and sys.path so that
    modules inside 'Linkedin Finder Agent' can resolve their own local packages
    (graph, config, configuration, utils, prompts, mcp_client, etc.) without
    colliding with 'Shortlister Agent'.
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    finder_dir = os.path.join(repo_root, "Linkedin Finder Agent")

    if not os.path.isdir(finder_dir):
        raise RuntimeError(
            f"[linkedin_finder_subgraph] Could not locate 'Linkedin Finder Agent' at: {finder_dir!r}"
        )

    clashing_names = [
        "graph", "config", "configuration", "utils", "prompts",
        "mcp_client", "output", "schemas", "logging_", "memory"
    ]

    # Stash any active modules from Shortlister Agent that collide with Linkedin Finder Agent
    saved_modules = {}
    for k in list(sys.modules.keys()):
        if any(k == c or k.startswith(f"{c}.") for c in clashing_names):
            saved_modules[k] = sys.modules.pop(k)

    orig_path = list(sys.path)
    if finder_dir not in sys.path:
        sys.path.insert(0, finder_dir)

    try:
        yield finder_dir
    finally:
        sys.path[:] = orig_path
        # Restore Shortlister Agent's original module objects
        for k, v in saved_modules.items():
            sys.modules[k] = v


def _get_contact_finder():
    global _cached_contact_finder
    if _cached_contact_finder is not None:
        return _cached_contact_finder

    with isolated_finder_context():
        from graph.contact_finder import contact_finder
        _cached_contact_finder = contact_finder
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
    from langgraph.checkpoint.memory import MemorySaver

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
        # Wrap execution in isolated_finder_context so any lazy imports inside graph execution
        # (e.g. MCP client / tool re-connections) resolve to Linkedin Finder Agent's packages
        with isolated_finder_context():
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
    parent_session_id: str | None = None,
) -> list[dict]:
    """Run the finder graph inside a correlated child logging context."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from logging_utils.context import bind_log_context
    from logging_utils.lifecycle import subagent_lifecycle

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
            component="graph.linkedin_finder_subgraph",
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
