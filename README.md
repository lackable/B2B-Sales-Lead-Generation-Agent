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
       │                   (Exports to Excel, CSV, and JSON)                       │
       └───────────────────────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

### 🔍 1. LinkedIn Finder Agent (`Linkedin Finder Agent/`)
- Built with **LangGraph StateGraph** architecture for resilient, stateful execution.
- Integrates any **OpenAI-compatible endpoint** (`OPENAI_BASE_URL` / `OPENAI_MODEL`) for intelligent query expansion and contact evaluation.
- Leverages **Bright Data MCP** (`streamable_http`) and **SerpAPI** for stealthy LinkedIn profile discovery and data extraction.
- Stores state checkpoints in SQLite (`memory.db`).

### 🎯 2. Shortlister Agent (`Shortlister Agent/`)
- Evaluates candidate companies and leads against strict quantitative qualification criteria.
- Integrates **Selenium WebDriver** for headless page inspection and data harvesting.
- Leverages financial screeners (`tradingview-screener`, `financedatabase`, `yfinance`) for market and revenue qualification.
- Performs automatic scoring and shortlists top prospects.

### 📧 3. Hunter.io Email Finder Utility (`hunter_linkedin_email_finder.py`)
- Resolves verified business email addresses using target LinkedIn profile URLs or handles (`/in/alexisohanian`).
- Provides confidence scoring, verification status, candidate position, company details, and source citations.
- Callable via standalone CLI or programmatically via FastAPI endpoints.

### ⚡ 4. FastAPI Orchestrator Backend (`backend/`)
- Runs agent pipelines in asynchronous subprocesses without blocking the event loop.
- **Teed Logging & WebSockets**: Broadcasts agent execution events and stdout live to connected UI clients.
- Export Builder converts raw JSON outputs into formatted **Excel (`.xlsx`)**, **CSV**, and **JSON** files.

### 🖥️ 5. React Real-Time Dashboard (`frontend/`)
- Interactive UI featuring `agent-run-visualizer`: a visual representation of agent workflow nodes and state transitions.
- Live stream console with color-coded log levels (INFO, WARN, ERROR, EVENT).
- Filterable lead table with one-click export downloads.

---

## 📁 Repository Structure

```
B2B Sales Lead Generation Bot/
├── .env.example                         # Root environment template (all components)
├── env_config.py                        # Central .env loader for root scripts & backend
├── requirements.txt                     # Consolidated Python dependencies (all components)
├── .gitignore                           # Git ignore rules (protects secret .env files)
├── start_backend.bat                    # Windows batch launcher for FastAPI backend
├── start_frontend.bat                   # Windows batch launcher for React frontend
├── hunter_linkedin_email_finder.py      # Standalone Hunter.io LinkedIn Email Finder CLI
├── printbrightdatatools.py              # Utility to inspect Bright Data MCP tool definitions
├── agent-run-visualizer (2).jsx         # Standalone React component for Agent graph visualization
├── consolidated_solution_flow.html     # Interactive solution architecture flow diagram
│
├── Linkedin Finder Agent/               # Autonomous LinkedIn Prospecting Agent
│   ├── main.py                          # Entry point for LinkedIn Finder Agent
│   ├── config.py / configuration.py     # Agent runtime configuration & models
│   ├── memory.db                        # SQLite state checkpoint persistence database
│   ├── graph/                           # LangGraph nodes and conditional edges
│   ├── prompts/                         # System prompts & LLM instructions
│   └── schemas/                         # Pydantic schemas for structured outputs
│
├── Shortlister Agent/                   # Autonomous Lead Qualification Agent
│   ├── main.py                          # Entry point for Shortlister Agent
│   ├── selenium_extractor.py            # Headless browser extraction logic
│   ├── memory.db                        # SQLite state persistence database
│   ├── graph/                           # Qualification state graph
│   └── data/                            # Default datasets & evaluation criteria
│
├── backend/                             # FastAPI Application & Export Engine
│   ├── main.py                          # FastAPI server endpoints & WebSocket hub
│   ├── config.py                        # Backend config (loads root .env via env_config)
│   ├── export_builder.py                # Excel/CSV export generation module
│   └── visualizer_broker.py             # Telemetry & state graph event broker
│
├── frontend/                            # Vite + React Dashboard UI
│   ├── package.json                     # React 19 dependencies & scripts
│   ├── vite.config.js                   # Vite server & build configuration
│   └── src/                             # Dashboard React components & hooks
│
├── logging_utils/                       # Shared Enterprise Logging Framework
│   ├── ws_broadcaster.py                # WebSocket log broadcasting queue
│   ├── redact.py                        # Sensitive token redactor (masks API keys)
│   └── context.py / handlers.py         # Structured log handlers
│
├── mcp_client/                          # Model Context Protocol (MCP) Client
└── output/                              # Output Directories
    ├── exports/                         # Generated Excel & CSV downloads
    ├── linkedin/                        # Raw LinkedIn Agent run outputs
    └── shortlister/                     # Raw Shortlister Agent run outputs
```

---

## ⚙️ Prerequisites

Ensure you have the following installed on your machine:

- **Python**: `3.10` or higher
- **Node.js**: `18.0` or higher (with `npm`)
- **Google Chrome**: (Required for Selenium web scraping features in Shortlister Agent)
- **Git**: For version control

---

## 🔑 Environment Setup

All components load **one** `.env` file from the repo root: `env_config.py`
(root scripts), `backend/config.py`, and each agent's `config.py` load it via
`load_dotenv`, and the Vite frontend reads `VITE_*` variables from the same file.

1. Copy the template:
   ```bash
   cp .env.example .env
   ```

2. Fill in your credentials — variable → consumer map:

   | Variable | Consumed by | Required |
   | :--- | :--- | :--- |
   | `HUNTER_API_KEY` | `env_config.py` → `hunter_linkedin_email_finder.py` (email enrichment) | For email finding |
   | `OPENAI_BASE_URL` | `backend/config.py`, both agents' `config.py` | Yes (no default) |
   | `OPENAI_API_KEY` | `backend/config.py`, both agents' `config.py` | Yes |
   | `OPENAI_MODEL` | `backend/config.py`, both agents' `config.py` | Yes |
   | `OPENAI_MODELS` | both agents' `config.py` (comma-separated rotation list; overrides `OPENAI_MODEL`) | Optional |
   | `OPENAI_INPUT_COST_PER_M`, `OPENAI_OUTPUT_COST_PER_M` | both agents' `config.py` (USD per million tokens for cost reporting) | Optional |
   | `RATE_LIMIT_CYCLE_WAIT_SECONDS` | both agents' `config.py` | Optional (default `65`) |
   | `BRIGHT_DATA_MCP_URL` | both agents' `config.py` | Yes |
   | `BRIGHT_DATA_API_KEY` | both agents' `config.py`, `printbrightdatatools.py` | Yes |
   | `SERPAPI_API_KEY` | `Linkedin Finder Agent/config.py` | Yes |
   | `LOG_LEVEL`, `LOG_DIR` | `logging_utils` | Optional (defaults `INFO`, `logs`) |
   | `CENTRAL_LOG_URL`, `CENTRAL_LOG_BATCH_SIZE`, `CENTRAL_LOG_FLUSH_INTERVAL_S` | `logging_utils` | Optional |
   | `VITE_API_BASE_URL` | `frontend/src/api.js` | Optional (default `http://localhost:8000`) |

   Accepted fallback aliases: `HUNTER_KEY` / `API_KEY` for `HUNTER_API_KEY`,
   and `BRIGHTDATA_TOKEN` for `BRIGHT_DATA_API_KEY`.

   `PIPELINE_RUN_ID` is injected at runtime by `backend/main.py` — do not set it in `.env`.

---

## 🚀 Quick Start Guide

### Option 1: One-Click Windows Launchers (Recommended)

1. Double-click **`start_backend.bat`** to start the FastAPI server on `http://localhost:8000`.
2. Double-click **`start_frontend.bat`** to start the React dashboard on `http://localhost:5173`.
3. Open your browser and navigate to `http://localhost:5173`.

---

### Option 2: Manual Terminal Setup

#### 1. Start the Backend
```bash
# From the repo root: install Python dependencies (all components)
pip install -r requirements.txt

# Navigate to backend directory
cd backend

# Run FastAPI backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

#### 2. Start the Frontend
```bash
# Navigate to frontend directory
cd frontend

# Install Node dependencies
npm install

# Run Vite dev server
npm run dev
```

---

## 🛠️ CLI Utilities & Standalone Tools

### Hunter.io LinkedIn Email Finder
Run email discovery directly from terminal:
```bash
python hunter_linkedin_email_finder.py -l "https://www.linkedin.com/in/alexisohanian/"
```
Options:
- `-l`, `--linkedin`: LinkedIn profile URL or handle (required)
- `-k`, `--api-key`: Hunter.io API key (optional if set in the root `.env`)
- `--domain`: Optional company domain (e.g. `reddit.com`)
- `--json`: Output response in raw JSON format

### Bright Data MCP Tools Inspector
Inspect available web scraping tools exposed by Bright Data MCP:
```bash
python printbrightdatatools.py
```

---

## 📡 API Reference Overview

The FastAPI backend exposes the following primary endpoints:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/run-shortlister` | Launches the Shortlister Agent with ICP parameters |
| `POST` | `/run-linkedin-finder` | Launches the LinkedIn Finder Agent for target contacts |
| `POST` | `/find-email` | Calls Hunter.io API to resolve LinkedIn handle to email |
| `GET` | `/ws/logs` | WebSocket endpoint for streaming real-time logs & events |
| `GET` | `/stream-logs` | SSE endpoint for streaming logs to web browsers |
| `GET` | `/exports/{type}/{filename}` | Downloads generated Excel (`.xlsx`), CSV, or JSON exports |

---

## 🛡️ Security & Privacy Best Practices

- **Never Commit `.env` Files**: `.env` files contain active API keys and are listed in `.gitignore`. Always use the root `.env.example` template for deployment.
- **Redaction**: All logging handlers use `logging_utils/redact.py` to scrub tokens, bearer authorization headers, and API keys before broadcasting to WebSockets.
- **Data Protection**: Ensure lead generation activities strictly follow applicable local data privacy laws (GDPR, CAN-SPAM, CCPA).

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
