# Work Changelog

## 2026-09-26 — Add a 642-test hermetic unit/integration suite [testing]

- Actor: Command Code
- Goal: Cover every function and logic branch of the restructured package so behavior is pinned before further changes.
- Changed: `tests/conftest.py`; `tests/unit/core/**` (telemetry ×10, config, llm, memory, clients ×2, exporters ×3); `tests/unit/agents/shortlister/**` (9 files); `tests/unit/agents/linkedin_finder/**` (4 files); `tests/unit/api/**` (6 files); `tests/unit/scripts/test_find_email.py`; `tests/integration/test_api_endpoints.py`; `pyproject.toml` (pytest-asyncio, ruff, `[tool.pytest.ini_options]`, `[tool.ruff]`).
- Implementation: Five subagents each owned a disjoint slice and wrote tests against module-mirroring paths; the lead wrote the shared fixtures and the 23 CLI-entry-point tests (the only modules no subagent covered). Existing suites were `git mv`-ed into their new homes and extended. Every external client (httpx, requests, MCP, ChatOpenAI, yfinance, financedatabase, Selenium) is monkeypatched; file writes go to `tmp_path`.
- Why: The plan required `pytest` to pass, but 2 of 7 existing tests never executed (no `pytest-asyncio`) and required a live MCP server; nothing else was covered.
- Verification: `.venv\Scripts\python.exe -m pytest -q` — passed (642 passed, 3 warnings); also passed with `-W error::RuntimeWarning`; timing-sensitive files re-run 3× without flakiness; `.venv\Scripts\python.exe -m ruff check .` — passed.
- Follow-up: The suite surfaced ~12 pre-existing defects; they are recorded in `LEARNINGS.md` and listed in `TASKS.md`. Nothing in `src/` was changed (see ADR-2026-09-26-5).
- Commit: uncommitted

## 2026-09-26 — Restructure into `src/leadgen` with `var/` data separation (phases 0-3) [structure, packaging, api]

- Actor: Command Code
- Goal: Turn a three-root script layout into one readable, installable package with code and runtime data fully separated, without changing behavior.
- Changed: new `src/leadgen/{config.py,core/**,agents/**,api/**}`; `pyproject.toml`; deleted `env_config.py`, `backend/`, `Linkedin Finder Agent/`, `Shortlister Agent/`, `logging_utils/`, all four config modules and `requirements.txt`; `var/` migration; `.gitignore`.
- Implementation: `git mv` throughout (47 renames). Four config modules merged into `src/leadgen/config.py`; `logging_utils/` + both agents' `logging_/` merged into `core/telemetry/` (`config.py` → `adapter.py`); both `bright_data_client.py` copies merged into `core/clients/bright_data.py` (union of both tool helpers); `backend/main.py` (1251 lines) split into `api/{app,state,runner,parsers,schemas,visualizer_broker}.py` + 6 routers; the `sys.modules` stash/swap in the subgraph bridge replaced by a plain import; subprocess launches switched to `python -m leadgen.agents.*` with cwd = repo root; 255 committed runtime files untracked and moved into `var/`.
- Why: Remove every `sys.path`/`sys.modules` hack, deduplicate shared modules, keep artifacts out of the source tree, and make the API readable by domain.
- Verification: `.venv\Scripts\python.exe -m compileall -q src scripts tests` — passed; `-m ruff check .` — passed; `-m pytest -q` — passed (13 tests at that point); live `uvicorn leadgen.api.app:app` served `/health`, both `/status` endpoints, `/linkedin/files` (83 workbooks), `/export/list`, `/linkedin/decision-makers` (68 contacts parsed from migrated data), a workbook download and a freshly built `/export/consolidated` (sheets `Company Overview, _dm_data, Decision Makers`); route table asserted to be exactly the original 19 HTTP + 2 WS endpoints; both `--help` CLIs exit 0.
- Follow-up: `git add -A` + commit the whole tree (see `TASKS.md`); investigate the defects in `LEARNINGS.md`.
- Commit: uncommitted

## 2026-09-26 — Tooling, docs, CI, containers, legacy cleanup (phase 5) [tooling, docs]

- Actor: Command Code
- Goal: Make the repo runnable, lintable and testable by a fresh checkout / CI, and document the new layout.
- Changed: `Makefile`, `deploy/Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `start_backend.bat`, `.env.example`, `README.md`, `.gitignore`, `scripts/{find_email.py,print_brightdata_tools.py,pivot_export.py}`, `docs/architecture/`.
- Implementation: Make targets `install/dev-api/dev-web/test/lint/format`; CI runs `ruff check .` + `pytest -q`; the API image installs the package and includes Chromium for Selenium; compose mounts `./var` so artifacts survive restarts; `start_backend.bat` now runs `uvicorn leadgen.api.app:app` from the repo root; README rewritten with the new tree, env-var → consumer map and the real endpoint list; the scratch `TestExport.py` became `scripts/pivot_export.py` with `--input/--output/--sheet` args instead of hardcoded foreign paths; the three solution-flow HTMLs were `git mv`-ed into `docs/architecture/` (the `OLD` one deleted).
- Why: The old launchers/README described directories and commands that no longer existed, and CI had to enforce the new lint/test setup.
- Verification: `.venv\Scripts\python.exe -m ruff check .` — passed; `-m pytest -q` — passed; `scripts/find_email.py --help` and `scripts/pivot_export.py --help` — exit 0; the Docker image itself was not built (not run).
- Follow-up: The compose/frontend path was not smoke-tested (`frontend/node_modules` is not installed locally); `docker compose up --build` remains unverified.
- Commit: uncommitted
