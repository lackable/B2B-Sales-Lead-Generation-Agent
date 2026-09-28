"""
leadgen — B2B sales lead generation suite.

Layout
------
config       single settings module (loads the repo-root .env)
core         shared building blocks: LLM helpers, checkpointer, API clients,
             exporters, structured telemetry
agents       the two LangGraph agents (``shortlister``, ``linkedin_finder``)
api          FastAPI orchestrator that runs the agents as subprocesses
"""

__version__ = "0.1.0"
