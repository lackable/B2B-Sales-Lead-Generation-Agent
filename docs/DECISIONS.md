# Decisions

## ADR-2026-09-26-5 — Behavior-preserving restructure: document bugs, do not fix them [process, structure]

- Status: accepted
- Context: The approved restructure plan required "Behavior stays identical throughout", but writing the test suite surfaced ~12 latent defects (see `LEARNINGS.md`).
- Decision: Fix nothing in `src/` that changes observable behavior during the restructure; report each finding and pin the current behavior with a test. Bugs are fixed later as separate, deliberate changes.
- Alternatives: (a) fix the defects while the files were open — rejected: mixes a large structural diff with behavior changes, and the user never asked for it; (b) leave them untested — rejected: silent regressions.
- Rationale: Keeps the (already very large) restructure reviewable and bisectable, and gives the user authority over behavior changes.
- Consequences: Some tests intentionally assert buggy behavior (with a docstring explaining why). Fixing a bug requires updating its pinning test in the same change. Open items are listed in `TASKS.md`.
- Related: `docs/LEARNINGS.md`, `docs/TASKS.md`, plan `~/.commandcode/plans/b2b-leadgen-production-restructure.md`

## ADR-2026-09-26-4 — Hermetic test suite mirroring the package layout [testing]

- Status: accepted
- Context: Only 7 test files existed; 2 of them (async verifier tests) never executed because `pytest-asyncio` was not installed, and they required a live Bright Data MCP connection.
- Decision: Adopt `pytest-asyncio` (strict mode) + `ruff` as dev extras; organise tests as `tests/unit/{core,agents,api,scripts}` mirroring `src/leadgen`, plus `tests/integration`; make every test hermetic via two shared fixtures in `tests/conftest.py` (`isolated_var` for all runtime paths, `api_state_reset` for the API singletons). Network clients, LLM, MCP, Selenium, yfinance and financedatabase are always monkeypatched.
- Alternatives: (a) keep folder-agnostic flat test files — rejected: duplicates basenames break pytest's prepend import mode and the mapping to source is unclear; (b) integration-style tests hitting real services — rejected: unusable in CI and non-deterministic.
- Rationale: 642 tests run in ~11 s with no credentials and no writes into `var/`, so they are safe in CI.
- Consequences: No `__init__.py` in test dirs, so **test file basenames must stay globally unique**. Tests that need live services would have to be marked/skipped explicitly.
- Related: `pyproject.toml`, `tests/conftest.py`, `.github/workflows/ci.yml`

## ADR-2026-09-26-3 — One settings module and one LLM cost default pair [config]

- Status: accepted
- Context: Four config modules existed (`env_config.py`, `backend/config.py`, and one per agent) with duplicated env reads; the two agents used different default token prices (0.150/0.600 vs 0.250/2.000).
- Decision: Collapse them into `src/leadgen/config.py`. Where the agents disagreed, the documented `.env.example` pair wins: `OPENAI_INPUT_COST_PER_M=0.250`, `OPENAI_OUTPUT_COST_PER_M=2.000`, overridable via env.
- Alternatives: (a) keep per-agent cost constants — rejected: a merged `PipelineLogger` cannot read two defaults and the duplication was the thing being removed; (b) pick 0.150/0.600 — rejected: contradicts `.env.example` documentation.
- Rationale: One place to read env, one reported cost model.
- Consequences: Shortlister's *reported* cost summary rises unless the env vars are set; actual spend is unaffected (cost is informational only).
- Related: `src/leadgen/config.py`, `src/leadgen/core/telemetry/callbacks.py`, `.env.example`

## ADR-2026-09-26-2 — Runtime artifacts collapse into `var/runs/<agent>` and legacy data is migrated in [data]

- Status: accepted
- Context: Agents wrote into `<Agent>/output/` inside the source tree and the API then *copied* each file to root `output/{linkedin,shortlister}/` for serving. 255 runtime files were committed to git.
- Decision: All artifacts live under gitignored `var/` (`runs/<agent>/`, `exports/`, `logs/`, `data/`). Agents write directly into the served directory, so `_sync_all_outputs` was deleted. The 255 committed artifacts were untracked, and their local copies were **moved** into `var/` (keeping the run history visible in the UI) rather than deleted. `Linkedin Finder Agent/memory.db` became `var/data/linkedin.db`.
- Alternatives: (a) keep the staging → serve copy step — rejected: duplicates every file for no benefit; (b) start with an empty `var/` — rejected: would silently drop the user's past reports; (c) delete the artifacts — rejected: destroys run history.
- Rationale: Code and data are fully separated, one copy of each file, and the dashboard still lists historical runs.
- Consequences: Existing file paths changed — anything (docs, scripts, muscle memory) pointing at `output/` is stale. `LEADGEN_VAR_DIR` overrides the root. Sub-`reports/` JSON snapshots and per-agent SQLite DBs keep their previous isolation.
- Related: `src/leadgen/config.py`, `src/leadgen/api/runner.py`, `.gitignore`

## ADR-2026-09-26-1 — Single installable package `leadgen` (src layout) [structure, packaging]

- Status: accepted
- Context: Three top-level Python "roots" (`backend/`, `Linkedin Finder Agent/`, `Shortlister Agent/`) each had their own `config`/`graph`/`utils` modules. Cross-agent use required a `sys.modules` stash/swap plus `sys.path` inserts, and each test file began with a `sys.path.insert` preamble.
- Decision: Move everything into one installable package `src/leadgen` (`pip install -e .`), with package entry points `python -m leadgen.agents.shortlister` / `python -m leadgen.agents.linkedin_finder`. The Shortlister → LinkedIn Finder subgraph is now a plain import.
- Alternatives: (a) keep separate roots and add a `conftest.py`-based path shim — rejected: the module-name collisions are structural, not a path problem; (b) namespace packages per agent without installation — rejected: still needs path manipulation at runtime and in the API subprocesses.
- Rationale: Removes every `sys.path`/`sys.modules` hack, makes both agents importable in one process, and lets `git mv` keep history for the moves.
- Consequences: Agents and API must run from an interpreter where `leadgen` is installed (the API spawns subprocesses with `sys.executable`). `frontend/` is intentionally untouched. `git mv` was used throughout so history follows files.
- Related: `pyproject.toml`, `src/leadgen/agents/shortlister/subgraphs/linkedin_finder.py`, plan `~/.commandcode/plans/b2b-leadgen-production-restructure.md`
