# 🚀 B2B Sales Lead Generation Bot Suite

An enterprise-grade, multi-agent AI system for automated B2B sales lead discovery, LinkedIn profile mining, contact enrichment, deep qualification scoring, and verified email retrieval.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-8.0-646CFF?logo=vite&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-orange)
![OpenAI Compatible](https://img.shields.io/badge/OpenAI--Compatible-Endpoint-412991?logo=openai&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 📌 Overview

The **B2B Sales Lead Generation Bot Suite** combines two autonomous **LangGraph AI Agents**, a high-performance **FastAPI orchestrator backend**, and a real-time **Vite/React telemetry dashboard**. It transforms raw ICP (Ideal Customer Profile) requirements into verified, high-converting B2B lead lists complete with verified corporate email addresses and LinkedIn profiles.

```
                  ┌─────────────────────────────────────────────────────────┐
                  │                 Vite / React Dashboard                  │
                  │        (Real-time State Graph & Log Telemetry)          │
                  └────────────────────────────┬────────────────────────────┘
                                               │ (REST / WebSockets / SSE)
                                               ▼
                  ┌─────────────────────────────────────────────────────────┐
                  │                    FastAPI Backend                      │
                  │      (runs each agent as `python -m leadgen.…`)         │
                  └──────────────┬───────────────────────────┬──────────────┘
                                 │                           │
                                 ▼                           ▼
       ┌───────────────────────────────────┐   ┌───────────────────────────────────┐
       │       LinkedIn Finder Agent       │   │         Shortlister Agent         │
       │  (LangGraph + Bright Data MCP +   │   │     (LangGraph + Selenium +       │
       │             SerpAPI)              │   │     Financial Screeners)          │
       └─────────────────┬─────────────────┘   └─────────────────┬─────────────────┘
                         │                                       │
                         └───────────────────┬───────────────────┘
                                             │
                                             ▼
       ┌───────────────────────────────────────────────────────────────────────────┐
       │                   Hunter.io Email Verification & Output                   │
       │            (Excel workbooks, consolidated exports, JSON snapshots)        │
       └───────────────────────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

### 🔍 1. LinkedIn Finder Agent (`leadgen.agents.linkedin_finder`)
- Built with **LangGraph StateGraph** architecture for resilient, stateful execution.
- Integrates any **OpenAI-compatible endpoint** (`OPENAI_BASE_URL` / `OPENAI_MODEL`) for intelligent query expansion and contact evaluation.
- Leverages **Bright Data MCP** (`streamable_http`) and **SerpAPI** for stealthy LinkedIn profile discovery and data extraction.
- Stores state checkpoints in SQLite (`var/data/linkedin.db`).

### 🎯 2. Shortlister Agent (`leadgen.agents.shortlister`)
- Evaluates candidate companies and leads against strict quantitative qualification criteria.
- Integrates **Selenium WebDriver** for headless page inspection and data harvesting.
- Leverages financial screeners (`tradingview-screener`, `financedatabase`, `yfinance`) for market and revenue qualification.
- Runs the LinkedIn Finder agent as a native in-process subgraph — no module swapping, just an import.
- Performs automatic scoring and shortlists top prospects.

### 📧 3. Hunter.io Email Finder (`leadgen.core.clients.hunter` + `scripts/find_email.py`)
- Resolves verified business email addresses using target LinkedIn profile URLs or handles (`/in/alexisohanian`).
- Provides confidence scoring, verification status, candidate position, company details, and source citations.
- Callable via standalone CLI or programmatically via FastAPI endpoints.

### ⚡ 4. FastAPI Orchestrator Backend (`leadgen.api`)
- Runs agent pipelines in asynchronous subprocesses without blocking the event loop.
- **Teed Logging & WebSockets**: Broadcasts agent execution events and stdout live to connected UI clients.
- Consolidated export builder turns raw agent output into formatted **Excel (`.xlsx`)** workbooks (Company Overview + Decision Makers).

### 🖥️ 5. React Real-Time Dashboard (`frontend/`)
- Interactive UI featuring `agent-run-visualizer`: a visual representation of agent workflow nodes and state transitions.
- Live stream console with color-coded log levels (INFO, WARN, ERROR, EVENT).
- Filterable lead table with one-click export downloads.

---

## 📁 Repository Structure

```
B2B-Sales-Lead-Generation-Agent/
├── pyproject.toml                       # deps + ruff + pytest config (pip install -e .)
├── Makefile                             # install / dev-api / dev-web / test / lint
├── docker-compose.yml                   # api + frontend
├── deploy/Dockerfile                    # API image (includes Chromium for Selenium)
├── .env.example                         # root environment template (all components)
├── start_backend.bat / start_frontend.bat
│
├── src/leadgen/                         # the installable Python package
│   ├── config.py                        # ONE settings module (loads the repo-root .env)
│   ├── core/
│   │   ├── llm.py                       # ChatOpenAI factory, rate-limit fallback, token guards
│   │   ├── memory.py                    # SQLite checkpointer factory
│   │   ├── clients/bright_data.py       # Bright Data MCP tool discovery + reconnect
│   │   ├── clients/hunter.py            # Hunter.io Email Finder API v2
│   │   ├── exporters/contacts.py        # per-company contact workbook
│   │   ├── exporters/report.py          # shortlister reports (Excel + JSON)
│   │   ├── exporters/builder.py         # consolidated 2-sheet API export
│   │   └── telemetry/                   # structured JSONL + WS telemetry
│   │                                    #   adapter, handlers, callbacks, log_store,
│   │                                    #   lifecycle, context, registry, redact,
│   │                                    #   snapshots, ws_broadcaster
│   ├── agents/
│   │   ├── linkedin_finder/             # graph, state, prompts, schemas, cli
│   │   └── shortlister/                 # graph, verifier, state, prompts, ticker,
│   │                                    #   scraping, cli, subgraphs/linkedin_finder
│   └── api/
│       ├── app.py                       # create_app: CORS, lifespan, routers
│       ├── state.py                     # AgentState, email store, WS client registry
│       ├── runner.py                    # subprocess runners, log fan-out, SSE
│       ├── parsers.py                   # Excel/URL/Hunter parsing helpers
│       ├── schemas.py                   # Pydantic request models
│       ├── visualizer_broker.py         # JSONL tailing → /ws/visualizer
│       └── routers/                     # shortlister, linkedin, hunter, exports, ws, health
│
├── frontend/                            # Vite + React dashboard UI
├── scripts/
│   ├── find_email.py                    # Hunter.io CLI
│   ├── print_brightdata_tools.py        # inspect Bright Data MCP tool schemas
│   └── pivot_export.py                  # filterable decision-maker export
├── tests/
│   ├── conftest.py                      # hermetic fixtures (isolated var/, API singletons)
│   ├── unit/                            # mirrors src/leadgen: core/, agents/, api/, scripts/
│   └── integration/                     # API endpoint round-trip, telemetry integrity
├── docs/architecture/                   # solution flow diagrams
├── deploy/                              # Dockerfile
└── var/                                 # GITIGNORED runtime artifacts
    ├── runs/shortlister/                # report_*.xlsx, reports/*.json
    ├── runs/linkedin/                   # contacts_*.xlsx, agent_state_*.json
    ├── exports/                         # consolidated API exports
    ├── logs/                            # run_*.jsonl telemetry
    └── data/                            # shortlister.db, linkedin.db
```

**Code and data are fully separated:** nothing is written into the source tree at runtime.
Every artifact lands under `var/` (override with `LEADGEN_VAR_DIR`).

---

## ⚙️ Prerequisites

- **Python**: `3.10` or higher
- **Node.js**: `18.0` or higher (with `npm`)
- **Google Chrome**: (Required for the Selenium web-scraping fallback in the Shortlister Agent)
- **Git**: For version control

---

## 🔑 Environment Setup

All components load **one** `.env` file from the repo root (`leadgen/config.py`), and the
Vite frontend reads `VITE_*` variables from the same file.

1. Copy the template:
   ```bash
   cp .env.example .env
   ```

2. Fill in your credentials — variable → consumer map:

   | Variable | Consumed by | Required |
   | :--- | :--- | :--- |
   | `LEADGEN_VAR_DIR` | `leadgen.config` (runtime artifact root, default `var/`) | Optional |
   | `HUNTER_API_KEY` | `leadgen.core.clients.hunter`, `/hunter/*` endpoints | For email finding |
   | `OPENAI_BASE_URL` | both agents, `leadgen.core.llm` | Yes (no default) |
   | `OPENAI_API_KEY` | both agents, `leadgen.core.llm` | Yes |
   | `OPENAI_MODEL` | both agents, `leadgen.core.llm` | Yes |
   | `OPENAI_MODELS` | `leadgen.core.llm` (comma-separated rotation list; overrides `OPENAI_MODEL`) | Optional |
   | `OPENAI_INPUT_COST_PER_M`, `OPENAI_OUTPUT_COST_PER_M` | `leadgen.core.telemetry.callbacks` (USD per million tokens for cost reporting) | Optional |
   | `RATE_LIMIT_CYCLE_WAIT_SECONDS` | `leadgen.core.llm` | Optional (default `65`) |
   | `BRIGHT_DATA_MCP_URL` | `leadgen.core.clients.bright_data` | Yes |
   | `BRIGHT_DATA_API_KEY` | `leadgen.core.clients.bright_data`, `scripts/print_brightdata_tools.py` | Yes |
   | `SERPAPI_API_KEY` | LinkedIn Finder agent | Yes |
   | `LOG_LEVEL`, `LOG_DIR` | `leadgen.core.telemetry` | Optional (defaults `INFO`, `var/logs`) |
   | `CENTRAL_LOG_URL`, `CENTRAL_LOG_BATCH_SIZE`, `CENTRAL_LOG_FLUSH_INTERVAL_S` | `leadgen.core.telemetry.handlers` | Optional |
   | `VITE_API_BASE_URL` | `frontend/src/api.js` | Optional (default `http://localhost:8000`) |

   Accepted fallback aliases: `HUNTER_KEY` / `API_KEY` for `HUNTER_API_KEY`,
   and `BRIGHTDATA_TOKEN` for `BRIGHT_DATA_API_KEY`.

   `PIPELINE_RUN_ID` is injected at runtime by the API — do not set it in `.env`.

---

## 🚀 Quick Start Guide

### Step 1 — Install the Python package (from the repo root)

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -e ".[dev]"
```

The editable install is what lets every module be imported as `leadgen.*` — there are no
`sys.path` hacks anywhere in the codebase.

### Option 1: One-Click Windows Launchers (Recommended)

1. Double-click **`start_backend.bat`** to start the FastAPI server on `http://localhost:8000`.
2. Double-click **`start_frontend.bat`** to start the React dashboard on `http://localhost:5173`.
3. Open your browser and navigate to `http://localhost:5173`.

### Option 2: Manual Terminal Setup

```bash
# Backend (repo root)
uvicorn leadgen.api.app:app --host 0.0.0.0 --port 8000 --reload

# Frontend (second terminal)
cd frontend
npm install
npm run dev
```

### Option 3: Docker Compose

```bash
cp .env.example .env      # fill in the API keys
docker compose up --build
```

`var/` is mounted into the api container so reports, exports and telemetry survive restarts.

### Common Make targets

```bash
make install     # pip install -e ".[dev]"
make dev-api     # uvicorn leadgen.api.app:app --reload
make dev-web     # cd frontend && npm run dev
make test        # pytest
make lint        # ruff check .
```

---

## 🛠️ CLI Utilities & Standalone Tools

### Running the agents directly

```bash
# Shortlister: pass the ICP query as an argument (prompts interactively if omitted)
python -m leadgen.agents.shortlister "Indian specialty chemical companies with revenue above 500 Cr"

# LinkedIn Finder: flags for one company (prompts interactively if --company_name is omitted)
python -m leadgen.agents.linkedin_finder --company_name "Acme Ltd" \
    --company_website https://acme.com --location India
```

### Hunter.io LinkedIn Email Finder

```bash
python scripts/find_email.py -l "https://www.linkedin.com/in/alexisohanian/"
```

Options: `-l/--linkedin` (required), `-k/--api-key`, `--first-name`, `--last-name`,
`--full-name`, `--domain`, `--company`, `--json`.

### Bright Data MCP Tools Inspector

```bash
python scripts/print_brightdata_tools.py
```

### Decision-Maker Pivot Export

Build a flat, AutoFilter-able sheet from a consolidated shortlister report:

```bash
python scripts/pivot_export.py --input var/runs/shortlister/report_consolidated_<timestamp>.xlsx
```

---

## 📡 API Reference Overview

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/shortlister/run` | Launch the Shortlister Agent with an ICP query |
| `GET` | `/shortlister/stream` | SSE stream of the Shortlister run log |
| `GET` | `/shortlister/status` | Status, parsed companies and latest report path |
| `GET` | `/shortlister/download` | Download the latest consolidated shortlist workbook |
| `POST` | `/linkedin/run` | Launch the LinkedIn Finder for a list of companies |
| `GET` | `/linkedin/stream` | SSE stream of the LinkedIn Finder run log |
| `GET` | `/linkedin/status` | Progress counters and the active companies |
| `GET` | `/linkedin/files` | List per-company contact workbooks |
| `GET` | `/linkedin/download/{filename}` | Download one contact workbook |
| `GET` | `/linkedin/decision-makers` | Parsed decision makers across processed companies |
| `POST` | `/hunter/find-email` | Resolve one LinkedIn handle to an email |
| `GET` | `/hunter/email-count` | Hunter indexed-email count for a domain (free) |
| `POST` | `/hunter/smart-enrich` | Batched, domain-gated email enrichment (max 3 per company) |
| `POST` | `/hunter/store-email` | Cache an email for the consolidated export |
| `GET` | `/export/consolidated` | Build + download the 2-sheet consolidated export |
| `GET` | `/export/list` | List previously generated exports |
| `GET` | `/export/download/{filename}` | Re-download a previous export |
| `POST` | `/reset` | Reset both agent states |
| `GET` | `/health` | Liveness probe |
| `WS` | `/ws/logs` | Structured JSON telemetry stream |
| `WS` | `/ws/visualizer` | State-graph visualizer event stream |

---

## 🧪 Testing & Linting

```bash
pytest              # unit + integration suites
ruff check .        # lint
```

CI (`.github/workflows/ci.yml`) runs both on every push and pull request.

---

## 🛡️ Security & Privacy Best Practices

- **Never Commit `.env` Files**: `.env` files contain active API keys and are listed in `.gitignore`. Always use the root `.env.example` template for deployment.
- **Redaction**: All logging handlers use `leadgen/core/telemetry/redact.py` to scrub tokens, bearer authorization headers, and API keys before broadcasting to WebSockets.
- **Data Protection**: Ensure lead generation activities strictly follow applicable local data privacy laws (GDPR, CAN-SPAM, CCPA).

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
