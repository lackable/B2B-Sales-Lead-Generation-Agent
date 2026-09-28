import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── Configurable Agent Parameters ─────────────────────────────────────────────
MAX_DECISION_MAKERS    = 5          # Maximum decision makers to extract
MAX_SCRAPE_CALLS       = 10         # Maximum BrightData/web-scrape tool calls in research loop

# ── LLM / OpenAI-compatible endpoint ──────────────────────────────────────────
OPENAI_BASE_URL        = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY         = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL           = os.getenv("OPENAI_MODEL")

raw_models = os.getenv("OPENAI_MODELS")
if raw_models:
    OPENAI_MODELS = [m.strip() for m in raw_models.split(",") if m.strip()]
elif OPENAI_MODEL:
    OPENAI_MODELS = [OPENAI_MODEL]
else:
    OPENAI_MODELS = []

RATE_LIMIT_CYCLE_WAIT_SECONDS = int(os.getenv("RATE_LIMIT_CYCLE_WAIT_SECONDS", "65"))

PER_MILLION_INPUT_TK_COST  = float(os.getenv("OPENAI_INPUT_COST_PER_M", "0.250"))
PER_MILLION_OUTPUT_TK_COST = float(os.getenv("OPENAI_OUTPUT_COST_PER_M", "2.000"))

# ── BrightData MCP ────────────────────────────────────────────────────────────
BRIGHT_DATA_MCP_URL    = os.getenv("BRIGHT_DATA_MCP_URL")
BRIGHT_DATA_API_KEY    = os.getenv("BRIGHT_DATA_API_KEY")

# ── SerpAPI ───────────────────────────────────────────────────────────────────
SERPAPI_API_KEY        = os.getenv("SERPAPI_API_KEY")

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR               = os.path.dirname(os.path.abspath(__file__))
MEMORY_DB_PATH         = os.path.join(BASE_DIR, "memory.db")
LOG_DIR                = os.path.join(BASE_DIR, "logs")
OUTPUT_DIR             = os.path.join(BASE_DIR, "output")

