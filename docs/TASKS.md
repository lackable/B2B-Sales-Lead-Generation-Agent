# Tasks

## Active
- [ ] Commit the restructure + test suite — entire working tree; HEAD `ecaaf71` still has the OLD layout (`backend/`, `Linkedin Finder Agent/`, `Shortlister Agent/`, `logging_utils/`, `env_config.py`, `requirements.txt` are deleted but staged/unstaged) — owner: Command Code @ 2026-09-26
  - Done: phases 0-5 of the restructure (`src/leadgen` package, `var/` data separation, API split into routers, tests, tooling/docs/CI) + 642-test suite
  - Touched: `src/**`, `tests/**`, `pyproject.toml`, `Makefile`, `README.md`, `.env.example`, `.gitignore`, `start_backend.bat`, `docker-compose.yml`, `deploy/`, `.github/workflows/ci.yml`, `docs/architecture/`
  - Verification: `.venv\Scripts\python.exe -m pytest -q` — passed (642 passed); `-m ruff check .` — passed
  - Risk: 40 untracked paths (`src/leadgen/**` new files, `tests/**` new files, `pyproject.toml`, `Makefile`, `deploy/`, `.github/`, `docker-compose.yml`, `scripts/find_email.py`) need `git add`; 47 renames + 280 deletions already staged
  - Next: `git add -A`, review with `git status`, then commit (user must approve)

## Blocked
- (none)

## Next
- `src/leadgen/api/parsers.py:68`: replace `host.lstrip("www.")` (strips a char set — `walmart.com` → `almart.com`) with a `startswith`-based strip; update the pinning test in `tests/unit/api/test_api_parsers.py`
- None guards (behavior change — confirm with user first): `agents/*/configuration.py` `from_runnable_config` → `config.get("configurable") or {}`; `agents/linkedin_finder/graph.py:513` `state.get("session_id") or "default_session"`; `agents/shortlister/cli.py` summary line formats `None` with `:<width` and crashes after a successful run
- `src/leadgen/core/exporters/builder.py:221` `_try_create_pivot` — dead (~120 lines): delete, or wire it in behind a flag
- Deprecations: `agents/linkedin_finder/graph.py:580` `config_schema=`/`input=` → `context_schema=`/`input_schema=`; `agents/shortlister/graph.py:755` `query_info.dict()` → `model_dump()`
