import os
from dotenv import load_dotenv

load_dotenv()

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

# Azure OpenAI
AZURE_ENDPOINT        = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_API_KEY         = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_DEPLOYMENT      = os.getenv("AZURE_OPENAI_DEPLOYMENT", "GPT-5-mini 2")
AZURE_DEPLOYMENT_FALLBACK = os.getenv("AZURE_OPENAI_DEPLOYMENT_FALLBACK", os.getenv("AZURE_OPENAI_DEPLOYMENT_2", "GPT-5-mini 3"))

raw_deployments = os.getenv("AZURE_OPENAI_DEPLOYMENTS")
if raw_deployments:
    AZURE_DEPLOYMENTS = [d.strip() for d in raw_deployments.split(",") if d.strip()]
else:
    AZURE_DEPLOYMENTS = [AZURE_DEPLOYMENT, AZURE_DEPLOYMENT_FALLBACK]

RATE_LIMIT_CYCLE_WAIT_SECONDS = int(os.getenv("RATE_LIMIT_CYCLE_WAIT_SECONDS", "65"))
AZURE_API_VERSION     = os.getenv("AZURE_OPENAI_API_VERSION")
