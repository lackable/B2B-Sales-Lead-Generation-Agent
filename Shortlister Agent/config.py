import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Screener defaults
SCREENER_MARKET       = "india"          # tradingview market key
SCREENER_LIMIT        = 60               # raw results to fetch
TOP_N_COMPANIES       = 10               # after cleaning, keep top N
DEDUP_BY_NAME         = True             # drop BSE duplicate if NSE present

# Paths
MEMORY_DB_PATH        = "memory.db"
EXCEL_OUTPUT_DIR      = "output/"
LOG_DIR               = "logs/"
DATA_DIR              = "data/"
REPORTS_OUTPUT_DIR    = "output/reports/"

# BrightData MCP
BRIGHT_DATA_MCP_URL   = os.getenv("BRIGHT_DATA_MCP_URL")
BRIGHT_DATA_API_KEY   = os.getenv("BRIGHT_DATA_API_KEY")

# OpenAI-compatible LLM endpoint
OPENAI_BASE_URL       = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY        = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL          = os.getenv("OPENAI_MODEL")

raw_models = os.getenv("OPENAI_MODELS")
if raw_models:
    OPENAI_MODELS = [m.strip() for m in raw_models.split(",") if m.strip()]
elif OPENAI_MODEL:
    OPENAI_MODELS = [OPENAI_MODEL]
else:
    OPENAI_MODELS = []

RATE_LIMIT_CYCLE_WAIT_SECONDS = int(os.getenv("RATE_LIMIT_CYCLE_WAIT_SECONDS", "65"))

PER_MILLION_INPUT_TK_COST  = float(os.getenv("OPENAI_INPUT_COST_PER_M", "0.150"))
PER_MILLION_OUTPUT_TK_COST = float(os.getenv("OPENAI_OUTPUT_COST_PER_M", "0.600"))
