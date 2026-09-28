# Learnings

## 2026-09-26 — `str.lstrip("www.")` corrupts domains starting with "w" [api, bug]

- Type: bug
- Finding: `src/leadgen/api/parsers.py:68` strips the *character set* `{w, .}` rather than the prefix, so `https://www.walmart.com` → `almart.com` and `https://web.com` → `eb.com`. The corrupted value is used as the domain for Hunter's email-count gate and email-finder calls.
- Evidence: `.venv\Scripts\python.exe -m pytest tests/unit/api/test_api_parsers.py -q` — passed, but the tests deliberately use non-`w` domains; direct check in the same test session reproduced `walmart.com` → `almart.com`.
- Implication: Silent wrong-domain lookups for a large set of real companies. Fix with `host[4:] if host.startswith("www.") else host` and update the pinning test (the agent wrote `test_www_prefix_is_stripped`-style assertions that still hold for non-`w` hosts).
- Related: `src/leadgen/api/parsers.py` (`extract_domain_from_url`), `TASKS.md`

## 2026-09-26 — Excel hyperlink extraction is lossy in two places [api, bug]

- Type: bug
- Finding: (a) `extract_url` (`parsers.py:29`) only follows a cell's `hyperlink.target` when it contains `http` or `linkedin.com`, so a bare-domain target (`acmecorp.com`) falls through and returns `""`; (b) `parse_shortlister_excel` (`parsers.py:112`) builds rows from `cell.value`, so a real openpyxl `hyperlink` attribute on the Website / LinkedIn columns is never read at all — only string values or `=HYPERLINK(...)` formulas-as-values survive.
- Evidence: `tests/unit/api/test_api_parsers.py` covers the scheme-less LinkedIn target (the only bare-domain shape the current gate accepts) and passes; bare-domain cases were verified to return `""`.
- Implication: Website/LinkedIn links can be missing from the parsed company list even though the workbook has them. Any fix must pass the *cell* (not `cell.value`) into `extract_url`.
- Related: `src/leadgen/api/parsers.py`, `src/leadgen/agents/shortlister/graph.py` (`linkedin_verifier`)

## 2026-09-26 — Shortlister CLI summary crashes on `None` company fields [agents, bug]

- Type: bug
- Finding: The final summary line in `agents/shortlister/cli.py` formats `ticker`, `website` and `linkedin_verified` with `:<width`, so a `None` raises `TypeError: unsupported format string passed to NoneType.__format__`. `pipeline_end` is emitted *before* that loop, so a successful run logs `pipeline_end` **and then** a spurious `pipeline_error` (files are already saved).
- Evidence: `tests/unit/agents/shortlister/test_shortlister_cli.py::test_summary_print_breaks_on_incomplete_company_records` pins the exact event order `["pipeline_start", "pipeline_end", "pipeline_error"]`.
- Implication: The pipeline normally fills every field, so this only fires on partially-populated records — but it makes a good run look failed. Fix by defaulting to `"N/A"`/`"NOT FOUND"` and update that test.
- Related: `src/leadgen/agents/shortlister/cli.py`, `TASKS.md`

## 2026-09-26 — `None`-valued inputs break three code paths [agents, bug]

- Type: bug
- Finding: (a) both `Configuration.from_runnable_config` implementations (`agents/shortlister/configuration.py`, `agents/linkedin_finder/configuration.py`) do `config.get("configurable", {}) if config else {}` — a present-but-`None` `configurable` makes them call `.get` on `None`; (b) `agents/linkedin_finder/graph.py:513` uses `state.get("session_id", "default_session")`, so a `None` session id yields `agent_state_None.json` / `contacts_<Company>_None.xlsx` and a broken download URL; (c) the same `None`-width formatting problem as the CLI summary (see above).
- Evidence: Direct calls reproduced the `AttributeError`; `tests/unit/agents/linkedin_finder/test_linkedin_graph.py` pins the `session_id=None` filename behaviour, and the shortlister configuration test covers `{}`, `None` and `{"configurable": {}}` but not a `None` value on purpose.
- Implication: Use `config.get("configurable") or {}` and `state.get("session_id") or "default_session"`. Fixing these two will fail the pinning tests — update them in the same commit.
- Related: `src/leadgen/agents/*/configuration.py`, `src/leadgen/agents/linkedin_finder/graph.py`, `TASKS.md`

## 2026-09-26 — Hunter fallback dict is unreachable for HTTP error responses [clients, bug]

- Type: bug
- Finding: `core/clients/hunter.py:96` calls `response.raise_for_status()` and only then returns `{"status_code": ..., "raw_response": ...}`. Since `raise_for_status()` raises on any 4xx/5xx, that fallback is only reachable for a 2xx response with a non-JSON body; a real 503 propagates `HTTPError` instead (the API turns it into a 500).
- Evidence: `tests/unit/agents/.../test_hunter.py` exercises the fallback line with a non-raising `raise_for_status` fake; the raising path shows the `HTTPError`.
- Implication: Decide the intended contract before changing it — returning the fallback dict would change `/hunter/find-email` error semantics from 500 to a 200-ish payload.
- Related: `src/leadgen/core/clients/hunter.py`, `src/leadgen/api/routers/hunter.py`

## 2026-09-26 — Dead code inventory found by the new tests [structure, discovery]

- Type: discovery
- Finding: (a) `core/exporters/builder.py:221` `_try_create_pivot` (~120 lines, the native PivotTable path the module docstring advertises) is never called — only `_write_grouped_table` runs; (b) `core/telemetry/callbacks.py:123-126` has a `try/except` whose branches are identical (no real fallback for `tiktoken.get_encoding`); (c) `agents/linkedin_finder/graph.py:202-205` has an unreachable retry backoff (`asyncio.sleep` sits after a `return` in the same branch), so connection-error retries fire with no delay; (d) `execute_tool_safely` in the same file returns `None` when `max_retries <= 0`; (e) `cli.py` has a second company-name guard that the interactive branch already makes unreachable.
- Evidence: `grep` for the symbols shows no callers; branch analysis is documented in the pinning tests (`test_bright_data.py`, `test_callbacks.py`, `test_linkedin_graph.py`).
- Implication: Delete (a), simplify (b) and (e), and either restore a delay or drop the dead branch in (c)/(d). None affect the happy path.
- Related: `src/leadgen/core/exporters/builder.py`, `src/leadgen/core/telemetry/callbacks.py`, `src/leadgen/agents/linkedin_finder/graph.py`

## 2026-09-26 — `WebSocketQueueHandler` writes an asyncio.Queue from a non-loop thread [telemetry, bug]

- Type: bug
- Finding: `core/telemetry/handlers.py` is driven by the `QueueListener` daemon thread, and its `emit` calls `ws_queue.put_nowait(...)` on a module-level `asyncio.Queue`, which is not thread-safe; waking a blocked reader must use `loop.call_soon_threadsafe`.
- Evidence: `tests/unit/core/telemetry/test_handlers.py` monkeypatches `ws_queue` with a per-test queue and shows delivery works inside one thread; the thread hand-off is the untested part.
- Implication: Benign today because agents run as *subprocesses*, so their `ws_queue` is never drained by the API's `/ws/logs` (that endpoint only sees events from the API process itself and from `runner.broadcast`). Fix only if agents ever move in-process.
- Related: `src/leadgen/core/telemetry/handlers.py`, `src/leadgen/core/telemetry/adapter.py`, `src/leadgen/api/runner.py`

## 2026-09-26 — pytest operational notes for this suite [testing, discovery]

- Type: discovery
- Finding: (a) `capsys.out` no longer exists — use `capsys.readouterr().out`; (b) there are no `__init__.py` files under `tests/`, so pytest's prepend import mode requires **globally unique test basenames** (hence `test_shortlister_graph.py` / `test_linkedin_graph.py` rather than two `test_graph.py`); (c) two of the seven original tests (`test_verifier_tools.py`) had never executed because `pytest-asyncio` was missing — they also needed a live Bright Data MCP; they now mock the researcher subgraph and `get_search_only_tools`; (d) `tests/unit/core/exporters/test_report_exporter.py` asserted column 10 while the `LinkedIn Confirmed?` column is 11 — it would have failed had it ever run.
- Evidence: `.venv\Scripts\python.exe -m pytest -q` — 642 passed, 0 skipped; the async tests only collected once `pytest-asyncio` was added.
- Implication: Keep `asyncio_mode = "strict"` and mark every async test; never introduce a duplicate test filename; do not assume a green suite means the tests ran before this date.
- Related: `pyproject.toml`, `tests/conftest.py`

## 2026-09-26 — Bulk data migrations must filter by extension [structure, correction]

- Type: correction
- Finding: The phase-0 migration moved "everything under `<Agent>/output/`" into `var/runs/<agent>/`, which also swept up `excel_exporter.py`, `consolidated_exporter.py`, `report_saver.py` and `TestExport.py` — real code living in a data directory. The staged renames made `git mv` report "bad source" until the files were restored with `git checkout --`.
- Evidence: `git status` showed the `.py` files as unstaged deletions while they sat in `var/`; the recovery was `git checkout -- <path>` followed by normal `git mv`.
- Implication: When separating code from data, drive the move from `git ls-files` filtered by extension, never from a directory glob. `var/` must never contain `.py` files.
- Related: `docs/PROJECT_CONTEXT.md` (Repository Map), `.gitignore`

## 2026-09-26 — Three non-fatal deprecation warnings remain [structure, discovery]

- Type: discovery
- Finding: `pytest -q` ends with 3 warnings from `src/`: `agents/linkedin_finder/graph.py:580` passes `config_schema=` and `input=` to `StateGraph` (LangGraph wants `context_schema=` / `input_schema=`; the shortlister graph already uses `context_schema`), and `agents/shortlister/graph.py:755` calls `query_info.dict()` (Pydantic v2 wants `model_dump()`).
- Evidence: `pytest -q` output summary, verified with `-W error::RuntimeWarning` that no *test-side* warning remains.
- Implication: Cosmetic today, breaking on the next major bumps. Safe to fix independently; `model_dump()` is exactly equivalent.
- Related: `src/leadgen/agents/linkedin_finder/graph.py`, `src/leadgen/agents/shortlister/graph.py`, `TASKS.md`
