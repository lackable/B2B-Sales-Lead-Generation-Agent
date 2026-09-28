"""
env_config — central environment loading for root-level scripts and the backend.

This is the ONLY place root-level code calls load_dotenv(). Named env_config
(not config) on purpose: the two agents each have their own `config` module and
`Shortlister Agent/graph/linkedin_finder_subgraph.py` swaps those by name when
it imports the LinkedIn agent in-process.

Consumers: hunter_linkedin_email_finder.py, printbrightdatatools.py,
backend/config.py. The agents load the same root .env from their own config.py.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent

load_dotenv(ROOT_DIR / ".env")

HUNTER_API_KEY = (
    os.getenv("HUNTER_API_KEY")
    or os.getenv("HUNTER_KEY")
    or os.getenv("API_KEY")
)

BRIGHT_DATA_API_KEY = os.getenv("BRIGHT_DATA_API_KEY") or os.getenv("BRIGHTDATA_TOKEN")
BRIGHT_DATA_MCP_URL = os.getenv("BRIGHT_DATA_MCP_URL")
