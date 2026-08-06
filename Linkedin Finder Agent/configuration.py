"""Configuration management for the Contact Finder agent."""

import os
from typing import Any, Optional
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

class Configuration(BaseModel):
    """Main configuration class for the Contact Finder agent."""
    
    max_structured_output_retries: int = Field(default=3)
    research_model: str = Field(default=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini-2"))
    research_model_max_tokens: int = Field(default=8192)

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
