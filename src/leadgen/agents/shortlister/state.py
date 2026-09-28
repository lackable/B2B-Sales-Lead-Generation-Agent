from typing import Annotated, Optional, TypedDict
import operator
from langchain_core.messages import MessageLikeRepresentation
from langgraph.graph import MessagesState
from pydantic import BaseModel, Field

###################
# Structured Outputs
###################

class ScreenerQuery(BaseModel):
    """Structured output from Step 1 LLM query formulator node."""
    sector: str = Field(description="TradingView Sector name (REQUIRED). Must match one of the exact TradingView sector names, e.g. 'Technology Services', 'Electronic Technology', 'Finance', 'Health Technology', 'Consumer Durables', 'Process Industries', etc.")
    industry: Optional[str] = Field(default=None, description="TradingView Sub-Industry name (OPTIONAL). Specific sub-industry string if explicitly requested or strongly implied (e.g. 'Information Technology Services', 'Packaged Software', 'Biotechnology', 'Major Banks'). Leave None if only sector is specified.")
    revenue_min: Optional[float] = Field(default=None, description="Minimum revenue in local currency units (e.g. INR in absolute terms: 5000000000 for 500 Cr)")
    revenue_max: Optional[float] = Field(default=None, description="Maximum revenue in local currency units")
    profit_min: Optional[float] = Field(default=None, description="Minimum net income in local currency units")
    profit_max: Optional[float] = Field(default=None, description="Maximum net income in local currency units")
    market: str = Field(default="india", description="TradingView market code, e.g. 'india'")
    location: Optional[str] = Field(default="India", description="Location or country string requested by user")
    limit: int = Field(default=60, description="Number of results to retrieve from TradingView (default 60)")

class ConductResearch(BaseModel):
    """Call this tool to conduct search for a company's official LinkedIn profile."""
    company_name: str = Field(description="Official name of the candidate company (REQUIRED).")
    website: str = Field(description="Official website URL or domain of the candidate company (REQUIRED).")
    description: Optional[str] = Field(default=None, description="Company business summary or description if available.")
    research_topic: str = Field(description="Detailed verification task description for the researcher sub-agent.")

class ResearchComplete(BaseModel):
    """Call this tool to indicate that the research/verification is complete."""

class CompanyRecord(TypedDict):
    ticker: str
    name: str
    industry: str
    revenue_ttm: Optional[float]
    net_income_ttm: Optional[float]
    employee_count: Optional[int]
    business_summary: Optional[str]
    website: Optional[str]
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]
    location: Optional[str]
    linkedin_verified: Optional[str]
    linkedin_confirmed: bool

###################
# State Reducers & Definitions
###################

def override_reducer(current_value, new_value):
    """Reducer function that allows overriding values in state."""
    if isinstance(new_value, dict) and new_value.get("type") == "override":
        return new_value.get("value", new_value)
    if isinstance(current_value, list):
        if isinstance(new_value, list):
            return current_value + new_value
        else:
            return current_value + [new_value]
    return new_value

class ShortlisterInputState(MessagesState):
    """Input state for Shortlister Agent graph."""
    pass

class ShortlisterState(MessagesState):
    """Main state for Shortlister Agent."""
    screener_query: Optional[ScreenerQuery] = None
    raw_companies: list[dict] = []
    enriched_companies: list[dict] = []
    cleaned_companies: list[dict] = []
    verified_companies: list[dict] = []
    
    # Verification subgraph sub-state
    supervisor_messages: Annotated[list[MessageLikeRepresentation], override_reducer] = []
    research_brief: Optional[str] = None
    raw_notes: Annotated[list[str], override_reducer] = []
    notes: Annotated[list[str], override_reducer] = []
    final_report: str = ""

class SupervisorState(TypedDict):
    """State for the supervisor node in the verification subgraph."""
    supervisor_messages: Annotated[list[MessageLikeRepresentation], override_reducer]
    research_brief: str
    notes: Annotated[list[str], override_reducer]
    research_iterations: int
    raw_notes: Annotated[list[str], override_reducer]
    shortlisted_companies: list[dict]

class ResearcherState(TypedDict):
    """State for individual researchers verifying candidates."""
    researcher_messages: Annotated[list[MessageLikeRepresentation], operator.add]
    tool_call_iterations: int
    research_topic: str
    compressed_research: str
    raw_notes: Annotated[list[str], override_reducer]

class ResearcherOutputState(BaseModel):
    """Output state from individual researchers."""
    compressed_research: str
    raw_notes: list[str] = Field(default_factory=list)
