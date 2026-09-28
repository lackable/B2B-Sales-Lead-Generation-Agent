"""
Process-wide runtime state shared by the routers and the background runners.

All of this lives in memory for the lifetime of the API process: the status of
each agent's current run, the Hunter email cache, the connected WebSocket clients
and the visualizer broker that tails the active run's JSONL telemetry.
"""

import asyncio
from typing import Dict, List, Optional

from leadgen.api.visualizer_broker import VisualizerBroker


class AgentState:
    """Status of one agent's current (or most recent) run."""

    def __init__(self):
        self.status: str = "idle"           # idle | running | done | error
        self.log_queues: List[asyncio.Queue] = []
        self.log_buffer: List[str] = []     # replay buffer for reconnecting clients
        self.last_excel: Optional[str] = None
        self.companies: List[Dict] = []
        self.current_company: Optional[str] = None
        self.active_companies: List[str] = []
        self.completed_count: int = 0
        self.total_count: int = 0
        self.user_query: str = ""
        self.extracted_location: str = ""
        self.error: Optional[str] = None

    def reset(self):
        self.status = "idle"
        self.log_queues.clear()
        self.log_buffer.clear()
        self.last_excel = None
        self.companies.clear()
        self.current_company = None
        self.active_companies.clear()
        self.completed_count = 0
        self.total_count = 0
        self.user_query = ""
        self.extracted_location = ""
        self.error = None


shortlister_state = AgentState()
linkedin_state = AgentState()

# In-memory email store, keyed by (company_name_lower, dm_name_lower) → email.
# Populated in real-time whenever Hunter finds an email in the frontend.
_email_store: Dict[tuple, str] = {}

# Connected WebSocket clients for structured log streaming
ws_log_clients: List = []

# Tails the active run's JSONL telemetry and fans it out to /ws/visualizer clients
visualizer_broker = VisualizerBroker()
