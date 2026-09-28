from typing import Literal, List
from pydantic import BaseModel, Field

class DecisionMaker(BaseModel):
    name: str = Field(description="Full name of the decision maker.")
    position: str = Field(description="Job title/position of the decision maker (e.g., CEO, Founder, VP Sales).")
    linkedin_url: str = Field(description="Full LinkedIn profile URL of the decision maker.")

class DecisionMakerList(BaseModel):
    decision_makers: List[DecisionMaker] = Field(default_factory=list, description="List of extracted decision makers.")

class ResearchLoopDecision(BaseModel):
    """LLM verdict after each scrape iteration to determine if more search calls are needed."""
    status: Literal["NEEDED", "NOT_NEEDED"] = Field(description="NEEDED if more decision makers/LinkedIn URLs are required, NOT_NEEDED if sufficient info gathered or limit reached.")
    reasoning: str = Field(description="One sentence rationale explaining the decision.")

class GeneratedQuery(BaseModel):
    query: str = Field(description="Optimized Google search query string only, targeted at decision makers.")
