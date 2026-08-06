"""Configuration management for the Shortlister Agent system."""

import os
from typing import Any, List, Optional
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

class Configuration(BaseModel):
    """Main configuration class for Shortlister Agent."""
    
    # Screener defaults
    screener_market: str = Field(default="india")
    screener_limit: int = Field(default=60)
    top_n_companies: int = Field(default=10)
    
    # Verifier iteration limits
    max_verifier_iterations: int = Field(default=15)
    max_concurrent_research_units: int = Field(default=20)
    max_react_tool_calls: int = Field(default=10)
    max_structured_output_retries: int = Field(default=3)
    
    # Model configuration
    query_model: str = Field(default=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini-2"))
    verifier_model: str = Field(default=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini-2"))
    compression_model: str = Field(default=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini-2"))
    
    # Pruning limit
    token_prune_limit: int = Field(default=350000)
    
    # Costs
    per_million_input_tk_cost: float = Field(default=0.250)
    per_million_output_tk_cost: float = Field(default=2.000)

    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> "Configuration":
        """Create a Configuration instance from a RunnableConfig."""
        configurable = config.get("configurable", {}) if config else {}
        field_names = list(cls.model_fields.keys())
        values: dict[str, Any] = {
            field_name: configurable.get(field_name)
            for field_name in field_names
            if configurable.get(field_name) is not None
        }
        return cls(**values)
