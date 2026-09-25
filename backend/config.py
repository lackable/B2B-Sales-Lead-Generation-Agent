"""
backend config — loads the repo-root .env (single source of truth) and exposes
the OpenAI-compatible LLM settings used by backend/main.py.

Re-exports env_config so load_dotenv() runs in exactly one place for root-level
code. The two agents load the same root .env from their own config.py.
"""

import os
import sys
from pathlib import Path

BASE_DIR: Path = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from env_config import ROOT_DIR  # noqa: E402,F401  (triggers the root .env load)

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL")

_raw_models = os.getenv("OPENAI_MODELS")
OPENAI_MODELS = (
    [m.strip() for m in _raw_models.split(",") if m.strip()]
    if _raw_models
    else ([OPENAI_MODEL] if OPENAI_MODEL else [])
)
