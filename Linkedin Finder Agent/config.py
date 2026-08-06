import os
from dotenv import load_dotenv

load_dotenv()

# ── Configurable Agent Parameters ─────────────────────────────────────────────
MAX_DECISION_MAKERS    = 5          # Maximum decision makers to extract
MAX_SCRAPE_CALLS       = 10         # Maximum BrightData/web-scrape tool calls in research loop

# ── LLM / Azure OpenAI ────────────────────────────────────────────────────────
AZURE_ENDPOINT         = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_KEY          = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_DEPLOYMENT       = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini-2")
AZURE_DEPLOYMENT_FALLBACK = os.getenv("AZURE_OPENAI_DEPLOYMENT_FALLBACK", os.getenv("AZURE_OPENAI_DEPLOYMENT_2", "gpt-5.4-mini"))

raw_deployments = os.getenv("AZURE_OPENAI_DEPLOYMENTS")
if raw_deployments:
    AZURE_DEPLOYMENTS = [d.strip() for d in raw_deployments.split(",") if d.strip()]
else:
    AZURE_DEPLOYMENTS = [AZURE_DEPLOYMENT, AZURE_DEPLOYMENT_FALLBACK]

RATE_LIMIT_CYCLE_WAIT_SECONDS = int(os.getenv("RATE_LIMIT_CYCLE_WAIT_SECONDS", "65"))
AZURE_API_VERSION      = os.getenv("AZURE_OPENAI_API_VERSION", "v1")

PER_MILLION_INPUT_TK_COST  = 0.250
PER_MILLION_OUTPUT_TK_COST = 2.000

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

