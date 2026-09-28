"""
Central settings for the whole suite.

This is the ONLY place ``load_dotenv()`` is called and the only module that reads
environment variables. Consumers: ``leadgen.agents.*``, ``leadgen.api.*``,
``leadgen.core.*`` and the ``scripts/`` entry points.

Every runtime artifact (per-run reports, exports, JSONL telemetry, checkpointer
databases) lives under ``var/`` — gitignored and outside the source tree, so code
and data stay fully separated.

Environment variables
---------------------
LEADGEN_VAR_DIR               override the artifact root (default: <repo>/var)
OPENAI_BASE_URL               OpenAI-compatible endpoint base URL
OPENAI_API_KEY                API key for the endpoint above
OPENAI_MODEL                  model sent as ``model=``
OPENAI_MODELS                 optional comma-separated rotation list (overrides OPENAI_MODEL)
OPENAI_INPUT_COST_PER_M       per-million input token cost in USD (run-end cost summary)
OPENAI_OUTPUT_COST_PER_M      per-million output token cost in USD
RATE_LIMIT_CYCLE_WAIT_SECONDS pause after exhausting the model rotation (default 65)
BRIGHT_DATA_MCP_URL           Bright Data MCP SSE endpoint
BRIGHT_DATA_API_KEY           Bright Data token (BRIGHTDATA_TOKEN is accepted as an alias)
SERPAPI_API_KEY               SerpAPI key (LinkedIn Finder query step)
HUNTER_API_KEY                Hunter.io key (HUNTER_KEY / API_KEY accepted as aliases)
LOG_LEVEL                     Python log level name (default INFO)
LOG_DIR                       JSONL telemetry directory (default: var/logs)
CENTRAL_LOG_URL               optional Loki/Elastic HTTP sink
CENTRAL_LOG_BATCH_SIZE        central log batch size (default 50)
CENTRAL_LOG_FLUSH_INTERVAL_S  central log flush interval in seconds (default 5)
APP_DB_URL                    SQLAlchemy URL for the auth database (default: <VAR_DIR>/data/app.db)
DB_AUTO_MIGRATE               run ``alembic upgrade head`` on API startup (default true)
SESSION_COOKIE_NAME           session cookie name (default leadgen_session)
SESSION_TTL_HOURS             absolute session lifetime in hours (default 168)
SESSION_IDLE_MINUTES          idle timeout in minutes (default 720)
COOKIE_SECURE                 set the cookie's Secure flag (default false)
CORS_ALLOWED_ORIGINS          comma-separated browser origins allowed to call the API
AUTH_MAX_FAILED_LOGINS        failed logins before an account is locked (default 5)
AUTH_LOCKOUT_MINUTES          lockout duration in minutes (default 15)
PASSWORD_MIN_LENGTH           minimum password length (default 12)
"""

import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# ── Repo root & environment ────────────────────────────────────────────────────
# src/leadgen/config.py → parents[2] is the repo root that holds .env
ROOT_DIR: Path = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

# ── Runtime artifact paths (absolute, gitignored) ──────────────────────────────
VAR_DIR: Path = Path(os.getenv("LEADGEN_VAR_DIR") or (ROOT_DIR / "var"))
DATA_DIR: Path = VAR_DIR / "data"
RUNS_DIR: Path = VAR_DIR / "runs"
EXPORTS_DIR: Path = VAR_DIR / "exports"
LOGS_DIR: Path = VAR_DIR / "logs"

SHORTLISTER_OUTPUT_DIR: Path = RUNS_DIR / "shortlister"
SHORTLISTER_REPORTS_DIR: Path = SHORTLISTER_OUTPUT_DIR / "reports"
LINKEDIN_OUTPUT_DIR: Path = RUNS_DIR / "linkedin"

# Agent-facing path settings (absolute strings, matching what the agents expect)
MEMORY_DB_PATH: str = str(DATA_DIR / "shortlister.db")
LINKEDIN_MEMORY_DB_PATH: str = str(DATA_DIR / "linkedin.db")
EXCEL_OUTPUT_DIR: str = str(SHORTLISTER_OUTPUT_DIR)
REPORTS_OUTPUT_DIR: str = str(SHORTLISTER_REPORTS_DIR)
OUTPUT_DIR: str = str(LINKEDIN_OUTPUT_DIR)
LOG_DIR: str = os.getenv("LOG_DIR") or str(LOGS_DIR)

# ── LinkedIn Finder agent tuning ───────────────────────────────────────────────
MAX_DECISION_MAKERS = 5     # Maximum decision makers to extract per company
MAX_SCRAPE_CALLS = 10       # Maximum BrightData/web-scrape tool calls in the research loop

# ── Shortlister agent tuning ───────────────────────────────────────────────────
SCREENER_MARKET = "india"   # tradingview market key
SCREENER_LIMIT = 60         # raw results to fetch
TOP_N_COMPANIES = 10        # after cleaning, keep top N
DEDUP_BY_NAME = True        # drop BSE duplicate if NSE present

# ── LLM / OpenAI-compatible endpoint ──────────────────────────────────────────
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL")

_raw_models = os.getenv("OPENAI_MODELS")
OPENAI_MODELS = (
    [m.strip() for m in _raw_models.split(",") if m.strip()]
    if _raw_models
    else ([OPENAI_MODEL] if OPENAI_MODEL else [])
)

RATE_LIMIT_CYCLE_WAIT_SECONDS = int(os.getenv("RATE_LIMIT_CYCLE_WAIT_SECONDS", "65"))

PER_MILLION_INPUT_TK_COST = float(os.getenv("OPENAI_INPUT_COST_PER_M", "0.250"))
PER_MILLION_OUTPUT_TK_COST = float(os.getenv("OPENAI_OUTPUT_COST_PER_M", "2.000"))

# ── Bright Data MCP ────────────────────────────────────────────────────────────
BRIGHT_DATA_MCP_URL = os.getenv("BRIGHT_DATA_MCP_URL")
BRIGHT_DATA_API_KEY = os.getenv("BRIGHT_DATA_API_KEY") or os.getenv("BRIGHTDATA_TOKEN")

# ── SerpAPI ────────────────────────────────────────────────────────────────────
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

# ── Hunter.io ──────────────────────────────────────────────────────────────────
HUNTER_API_KEY = (
    os.getenv("HUNTER_API_KEY")
    or os.getenv("HUNTER_KEY")
    or os.getenv("API_KEY")
)


# ── Auth database & sessions ───────────────────────────────────────────────────
def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean env var; anything other than 1/true/yes/on is false."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# None → <VAR_DIR>/data/app.db, resolved lazily by database_url() so the tests
# can point the whole suite at a temp directory.
APP_DB_URL = os.getenv("APP_DB_URL")
DB_AUTO_MIGRATE = _env_flag("DB_AUTO_MIGRATE", True)

SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "leadgen_session")
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "168"))
SESSION_IDLE_MINUTES = int(os.getenv("SESSION_IDLE_MINUTES", "720"))
COOKIE_SECURE = _env_flag("COOKIE_SECURE", False)

# The dev frontend (5173) and API (8000) are different origins but the same site.
CORS_ALLOWED_ORIGINS = _env_list("CORS_ALLOWED_ORIGINS", ["http://localhost:5173"])

AUTH_MAX_FAILED_LOGINS = int(os.getenv("AUTH_MAX_FAILED_LOGINS", "5"))
AUTH_LOCKOUT_MINUTES = int(os.getenv("AUTH_LOCKOUT_MINUTES", "15"))
PASSWORD_MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", "12"))


def database_url() -> str:
    """The auth database URL: ``APP_DB_URL`` or ``<VAR_DIR>/data/app.db``."""
    if APP_DB_URL:
        return APP_DB_URL
    return f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}"


def ensure_runtime_dirs() -> None:
    """Create every gitignored artifact directory. Safe to call repeatedly."""
    for path in (
        DATA_DIR,
        EXPORTS_DIR,
        LOGS_DIR,
        SHORTLISTER_OUTPUT_DIR,
        SHORTLISTER_REPORTS_DIR,
        LINKEDIN_OUTPUT_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
