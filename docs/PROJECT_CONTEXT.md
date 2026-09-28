# Project Context

Last verified: ecaaf71 (2026-09-26) — NOTE: HEAD predates the uncommitted `src/leadgen` restructure + test suite that lives in the working tree; see `TASKS.md`.

## Purpose
B2B sales lead generation suite. Two autonomous LangGraph agents (Shortlister: screen companies and shortlist them; LinkedIn Finder: discover decision makers and their LinkedIn profiles) run behind a FastAPI orchestrator with a real-time React dashboard. Output is Excel workbooks of verified companies plus contacts enriched with Hunter.io emails.

## Repository Map
- `AGENTS.md` — tells agents that project memory lives in `docs/`
- `pyproject.toml`, `Makefile`, `docker-compose.yml`, `deploy/Dockerfile`, `.github/workflows/ci.yml` — packaging, tasks, containers, CI
- `src/leadgen/config.py` — the only module that reads env / calls `load_dotenv`
- `src/leadgen/core/` — `llm.py` (ChatOpenAI factory + rate-limit rotation), `memory.py` (SQLite checkpointer), `clients/{bright_data,hunter}.py`, `exporters/{contacts,report,builder}.py`, `telemetry/` (adapter, handlers, callbacks, log_store, registry, lifecycle, context, redact, snapshots, ws_broadcaster)
- `src/leadgen/agents/shortlister/` — `graph.py` (6 nodes), `verifier.py` (supervisor + researcher subgraphs), `state.py`, `prompts.py`, `ticker.py`, `scraping.py`, `cli.py`, `subgraphs/linkedin_finder.py`
- `src/leadgen/agents/linkedin_finder/` — `graph.py` (4 nodes), `state.py`, `prompts.py`, `schemas.py`, `cli.py`
- `src/leadgen/api/` — `app.py` (`create_app`), `runner.py`, `parsers.py`, `state.py`, `schemas.py`, `visualizer_broker.py`, `routers/{shortlister,linkedin,hunter,exports,ws,health}.py`
- `frontend/` — Vite + React 19 dashboard (untouched by the restructure)
- `scripts/` — `find_email.py`, `print_brightdata_tools.py`, `pivot_export.py`
- `tests/conftest.py`, `tests/unit/{core,agents,api,scripts}/`, `tests/integration/`
- `docs/architecture/*.html` — solution-flow diagrams
- `var/` — GITIGNORED runtime artifacts: `runs/{shortlister,linkedin}/`, `runs/shortlister/reports/`, `exports/`, `logs/`, `data/`

## Architecture
Request flow: React dashboard → FastAPI (REST + SSE + WebSocket) → each agent is launched as a **subprocess** `python -m leadgen.agents.<agent>` from the repo root (env `PIPELINE_RUN_ID` injected).

- Agents write results straight into `var/runs/<agent>/` (served by the API) and emit JSONL telemetry to `var/logs/run_<id>.jsonl`, which `api/visualizer_broker.py` tails to `/ws/visualizer`; stdout is teed to the browser over SSE (`/<agent>/stream`) and `/ws/logs`.
- Shortlister node chain: `query_formulator` (LLM → ScreenerQuery) → `screener_fetch` (TradingView) → `yfinance_enricher` → `cleaner` (drop has no website, top N) → `linkedin_verifier` (per company in parallel: Selenium homepage extraction + LLM researcher subgraph, alongside the LinkedIn Finder graph invoked **in-process** via `subgraphs/linkedin_finder.py`) → `excel_exporter_node` (`core/exporters/report.py::save_all`).
- LinkedIn Finder chain: `llm_query_generator` (SerpAPI query) → `serp_search` → `research_loop` (Bright Data MCP; limits `MAX_DECISION_MAKERS=5`, `MAX_SCRAPE_CALLS=10`) → `output_node` (contacts xlsx + `agent_state_*.json`).
- `GET /export/consolidated` builds the 2-sheet workbook (Company Overview / Decision Makers) from stored state via `core/exporters/builder.py`.

## Runtime / Tooling
- Python 3.12.10 in `.venv` (`requires-python >=3.10`); dependencies in `pyproject.toml`; install with `pip install -e ".[dev]"`.
- API: `uvicorn leadgen.api.app:app --host 0.0.0.0 --port 8000 --reload` from the repo root (or `start_backend.bat`).
- Frontend: `cd frontend && npm install && npm run dev` → http://localhost:5173 (or `start_frontend.bat`). Vite reads `VITE_*` from the root `.env` (`envDir: '..'`).
- Agents directly: `python -m leadgen.agents.shortlister "<query>"`; `python -m leadgen.agents.linkedin_finder --company_name "X" --company_website URL --location India`.
- Containers: `docker compose up --build` (api + web; `var/` mounted into the api container).
- Make targets: `install`, `dev-api`, `dev-web`, `test`, `lint`, `format`.

## Important Integrations
- OpenAI-compatible LLM — both agents, API location extraction, telemetry cost summary — `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_MODELS`
- Bright Data MCP (SSE transport) — scraping/search tool provider — `BRIGHT_DATA_MCP_URL` / `BRIGHT_DATA_API_KEY`
- SerpAPI — LinkedIn Finder query step — `SERPAPI_API_KEY`
- Hunter.io — email finder + domain email-count — `HUNTER_API_KEY`
- TradingView screener, yfinance, financedatabase — company screening/enrichment (no credentials)
- Selenium + Chrome/ChromeDriver — deterministic company LinkedIn URL extraction (requires Chrome installed)

## Conventions
- Everything is imported as `leadgen.*`; there are **no `sys.path` hacks** — the editable install is what makes imports work.
- Only `src/leadgen/config.py` touches env/`.env`; other modules import `from leadgen import config`.
- Runtime data is never written into the source tree — always under `var/` (override with `LEADGEN_VAR_DIR`).
- Structured telemetry goes through `leadgen.core.telemetry` (`logger.event(...)` / `emit_event(...)`); `print`/`log_print` are for human-readable agent output.
- Agent entry points are `cli.py` + `__main__.py` per agent package.
- Tests: pytest with `pytest-asyncio` in strict mode (mark every async test), hermetic (no network; use the `isolated_var` / `api_state_reset` fixtures in `tests/conftest.py`), and test file basenames must be unique across the suite.
- Lint: ruff, `line-length = 120`, `select = ["E4", "E7", "E9", "F"]`, excluding `var/`, `docs/`, `frontend/`.
- Use `git mv` when moving files so history follows.

## Constraints
- The 21 HTTP/WS endpoint paths and response shapes are a contract with `frontend/` — see `tests/unit/api/test_api_routes.py` and `tests/integration/test_api_endpoints.py`.
- The restructure was explicitly **behavior-preserving**: known bugs were documented in `LEARNINGS.md` and deliberately not fixed. Do not "fix" them silently — update the pinning test and record it.
- One `.env` at the repo root only (frontend included).
- API and agents must share one interpreter: subprocesses are launched with `sys.executable`, so the editable install must be present in that venv.
- `PIPELINE_RUN_ID` is runtime-injected by the API — never set it in `.env`.

## Verification Commands
- Tests: `.venv\Scripts\python.exe -m pytest -q` (642 tests, ~11 s)
- Lint: `.venv\Scripts\python.exe -m ruff check .`
- Import sanity: `.venv\Scripts\python.exe -m compileall -q src scripts tests`
- API smoke: start uvicorn, then GET `/health`, `/shortlister/status`, `/linkedin/status`
- CLI smoke: `python -m leadgen.agents.shortlister --help` and `python -m leadgen.agents.linkedin_finder --help` (both exit 0)

## Authoritative References
- `AGENTS.md` — entry point for agents; points at `docs/` memory
- `README.md` — user-facing overview, env-var → consumer map, API reference, run commands
- `docs/architecture/*.html` — solution-flow diagrams (3 files; `shortlister_solution_flow_legacy.html` is the older agent-level one)
- `tests/` — executable specification of behavior
- `docs/LEARNINGS.md` — pre-existing bugs and quirks found while writing the tests
