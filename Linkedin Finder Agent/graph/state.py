from typing import Annotated, Optional
import operator
from typing_extensions import TypedDict

class AgentInputState(TypedDict):
    company_name: str
    company_linkedin: str
    company_website: str
    location: str

class AgentState(TypedDict):
    # Input fields
    company_name: str
    company_linkedin: str
    company_website: str
    location: str

    # Node 1 output
    generated_query: str

    # Node 2 output
    serp_raw_response: dict
    ai_overview: str

    # Node 3 output (append-only via operator.add for lists)
    decision_makers: Annotated[list[dict], operator.add]
    scrape_calls_used: int
    loop_memory: Annotated[list[dict], operator.add]

    # Session metadata
    session_id: str
