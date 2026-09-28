"""Unit tests for the FastAPI app surface (``app.py``) and every router endpoint."""

import os
import re
import time
from pathlib import Path

import pytest
from fastapi import BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from sse_starlette.sse import EventSourceResponse

from leadgen import config
from leadgen.api import runner as runner_module
from leadgen.api import state as api_state
from leadgen.api import app as app_module
from leadgen.api.routers import exports as exports_router
from leadgen.api.routers import health as health_router
from leadgen.api.routers import hunter as hunter_router
from leadgen.api.routers import linkedin as linkedin_router
from leadgen.api.routers import shortlister as shortlister_router
from leadgen.api.routers import ws as ws_router
from leadgen.api.schemas import (
    HunterEmailRequest,
    HunterSmartEnrichRequest,
    LinkedInRequest,
    ShortlisterRequest,
    StoreEmailRequest,
)

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}

EXPECTED_HTTP_SURFACE = {
    ("/shortlister/run", "post"),
    ("/shortlister/stream", "get"),
    ("/shortlister/status", "get"),
    ("/shortlister/download", "get"),
    ("/linkedin/run", "post"),
    ("/linkedin/stream", "get"),
    ("/linkedin/status", "get"),
    ("/linkedin/files", "get"),
    ("/linkedin/download/{filename}", "get"),
    ("/linkedin/decision-makers", "get"),
    ("/hunter/find-email", "post"),
    ("/hunter/smart-enrich", "post"),
    ("/hunter/store-email", "post"),
    ("/hunter/email-count", "get"),
    ("/export/consolidated", "get"),
    ("/export/list", "get"),
    ("/export/download/{filename}", "get"),
    ("/reset", "post"),
    ("/health", "get"),
}

COMPANY_DICT = {
    "company_name": "Acme Corp",
    "linkedin_url": "https://linkedin.com/company/acme",
    "website": "https://acme.com",
}


def route_pairs(router):
    """(path, method) pairs for every HTTP route, skipping WebSocket routes."""
    return {
        (route.path, method.lower())
        for route in router.routes
        for method in getattr(route, "methods", None) or set()
    }


def included_routers(app):
    """Yield the original APIRouter behind each ``_IncludedRouter`` wrapper."""
    for route in app.routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            yield original


def websocket_paths(app):
    """Collect every WebSocket path, unwrapping FastAPI's lazy ``_IncludedRouter``."""
    found = {}
    for route in app.routes:
        original = getattr(route, "original_router", None)
        for candidate in (original.routes if original is not None else [route]):
            if type(candidate).__name__ == "APIWebSocketRoute":
                found[candidate.path] = candidate.name
    return found


class FakeRequest:
    def __init__(self, disconnected=True):
        self._disconnected = disconnected

    async def is_disconnected(self):
        return self._disconnected


@pytest.fixture
def runtime_dirs(isolated_var):
    """Point every configured artifact directory at tmp_path and create them."""
    for path in (
        config.LINKEDIN_OUTPUT_DIR,
        config.SHORTLISTER_OUTPUT_DIR,
        config.SHORTLISTER_REPORTS_DIR,
        config.EXPORTS_DIR,
        config.LOGS_DIR,
        config.DATA_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return isolated_var


# ──────────────────────────────────────────────────────────────────────────────
# HTTP surface
# ──────────────────────────────────────────────────────────────────────────────
class TestAppSurface:
    def test_openapi_http_surface_is_exactly_the_expected_nineteen_pairs(self):
        paths = app_module.app.openapi()["paths"]

        surface = {(path, method) for path, operations in paths.items() for method in operations if method in HTTP_METHODS}

        assert surface == EXPECTED_HTTP_SURFACE
        assert len(surface) == 19

    def test_same_surface_is_derived_from_the_app_routes(self):
        surface = set()
        for router in included_routers(app_module.app):
            surface |= route_pairs(router)

        assert surface == EXPECTED_HTTP_SURFACE

    @pytest.mark.parametrize(
        "router_module, expected",
        [
            (health_router, {("/health", "get")}),
            (
                shortlister_router,
                {
                    ("/shortlister/run", "post"),
                    ("/shortlister/stream", "get"),
                    ("/shortlister/status", "get"),
                    ("/shortlister/download", "get"),
                },
            ),
            (
                linkedin_router,
                {
                    ("/linkedin/run", "post"),
                    ("/linkedin/stream", "get"),
                    ("/linkedin/status", "get"),
                    ("/linkedin/files", "get"),
                    ("/linkedin/download/{filename}", "get"),
                    ("/linkedin/decision-makers", "get"),
                },
            ),
            (
                hunter_router,
                {
                    ("/hunter/find-email", "post"),
                    ("/hunter/smart-enrich", "post"),
                    ("/hunter/store-email", "post"),
                    ("/hunter/email-count", "get"),
                },
            ),
            (
                exports_router,
                {
                    ("/export/consolidated", "get"),
                    ("/export/list", "get"),
                    ("/export/download/{filename}", "get"),
                    ("/reset", "post"),
                },
            ),
        ],
    )
    def test_each_domain_router_exposes_its_own_paths(self, router_module, expected):
        assert route_pairs(router_module.router) == expected

    def test_websocket_paths_are_included_routers(self):
        assert websocket_paths(app_module.app) == {"/ws/logs": "ws_logs", "/ws/visualizer": "ws_visualizer"}
        assert websocket_paths(app_module.create_app()) == {"/ws/logs": "ws_logs", "/ws/visualizer": "ws_visualizer"}
        assert [route.path for route in ws_router.router.routes] == ["/ws/visualizer", "/ws/logs"]

    def test_openapi_does_not_leak_websocket_paths(self):
        assert "/ws/logs" not in app_module.app.openapi()["paths"]
        assert "/ws/visualizer" not in app_module.app.openapi()["paths"]

    def test_create_app_returns_a_fresh_app_with_cors_configured(self):
        fresh = app_module.create_app()

        assert fresh is not app_module.app
        assert fresh.title == "Agent Pipeline API"
        assert len(fresh.routes) == len(app_module.app.routes)

        cors = [middleware for middleware in fresh.user_middleware if middleware.cls is CORSMiddleware]
        assert len(cors) == 1
        assert cors[0].kwargs == {
            "allow_origins": ["*"],
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }

    def test_module_level_app_has_cors_configured_too(self):
        cors = [middleware for middleware in app_module.app.user_middleware if middleware.cls is CORSMiddleware]

        assert len(cors) == 1
        assert cors[0].kwargs["allow_origins"] == ["*"]

    @pytest.mark.asyncio
    async def test_lifespan_creates_the_runtime_directories(self, isolated_var):
        created = (
            config.DATA_DIR,
            config.EXPORTS_DIR,
            config.LOGS_DIR,
            config.SHORTLISTER_OUTPUT_DIR,
            config.SHORTLISTER_REPORTS_DIR,
            config.LINKEDIN_OUTPUT_DIR,
        )
        assert [path.exists() for path in created] == [False] * len(created)

        async with app_module.lifespan(app_module.app) as yielded:
            assert yielded is None

        assert [path.is_dir() for path in created] == [True] * len(created)


# ──────────────────────────────────────────────────────────────────────────────
# Health + reset
# ──────────────────────────────────────────────────────────────────────────────
class TestHealthAndReset:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self):
        assert await health_router.health() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_reset_clears_both_agent_states(self, api_state_reset):
        api_state.shortlister_state.status = "running"
        api_state.shortlister_state.user_query = "indian it companies"
        api_state.shortlister_state.extracted_location = "India"
        api_state.linkedin_state.status = "error"
        api_state.linkedin_state.error = "boom"
        api_state.linkedin_state.current_company = "Acme Corp"

        assert await exports_router.reset_all() == {"status": "reset"}

        assert api_state.shortlister_state.status == "idle"
        assert api_state.shortlister_state.user_query == ""
        assert api_state.shortlister_state.extracted_location == ""
        assert api_state.linkedin_state.status == "idle"
        assert api_state.linkedin_state.error is None
        assert api_state.linkedin_state.current_company is None


# ──────────────────────────────────────────────────────────────────────────────
# LinkedIn Finder routes
# ──────────────────────────────────────────────────────────────────────────────
class TestLinkedInRoutes:
    @pytest.mark.asyncio
    async def test_run_rejects_a_second_concurrent_run(self, api_state_reset):
        api_state.linkedin_state.status = "running"
        background = BackgroundTasks()

        with pytest.raises(HTTPException) as exc_info:
            await linkedin_router.run_linkedin(LinkedInRequest(companies=[COMPANY_DICT]), background)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "LinkedIn Finder is already running"
        assert background.tasks == []

    @pytest.mark.asyncio
    async def test_run_resets_state_and_schedules_the_background_task(self, api_state_reset):
        api_state.linkedin_state.status = "done"
        api_state.linkedin_state.error = "old error"
        api_state.linkedin_state.completed_count = 4
        api_state.linkedin_state.current_company = "Old Co"
        background = BackgroundTasks()

        request = LinkedInRequest(companies=[COMPANY_DICT], concurrency=3)
        result = await linkedin_router.run_linkedin(request, background)

        assert result == {"status": "started", "concurrency": 3}
        assert api_state.linkedin_state.status == "idle"
        assert api_state.linkedin_state.error is None
        assert api_state.linkedin_state.completed_count == 0
        assert api_state.linkedin_state.current_company is None

        assert len(background.tasks) == 1
        task = background.tasks[0]
        assert task.func is runner_module.run_linkedin_bg
        assert task.args == ([COMPANY_DICT], 3)
        assert task.kwargs == {}

    @pytest.mark.asyncio
    async def test_status_reports_the_current_state(self, api_state_reset):
        api_state.linkedin_state.status = "running"
        api_state.linkedin_state.current_company = "Acme Corp"
        api_state.linkedin_state.active_companies = ["Acme Corp", "Beta Ltd"]
        api_state.linkedin_state.completed_count = 1
        api_state.linkedin_state.total_count = 2
        api_state.linkedin_state.error = None

        assert await linkedin_router.linkedin_status() == {
            "status": "running",
            "current_company": "Acme Corp",
            "active_companies": ["Acme Corp", "Beta Ltd"],
            "completed_count": 1,
            "total_count": 2,
            "error": None,
        }

    @pytest.mark.asyncio
    async def test_stream_returns_an_event_source_response(self, api_state_reset):
        response = await linkedin_router.linkedin_stream(FakeRequest())

        assert isinstance(response, EventSourceResponse)
        assert response.status_code == 200
        assert response.media_type == "text/event-stream"

    @pytest.mark.asyncio
    async def test_files_returns_empty_when_output_dir_is_missing(self, isolated_var):
        assert config.LINKEDIN_OUTPUT_DIR.exists() is False

        assert await linkedin_router.linkedin_files() == {"files": []}

    @pytest.mark.asyncio
    async def test_files_lists_only_xlsx_sorted_by_mtime_desc(self, runtime_dirs):
        output_dir = config.LINKEDIN_OUTPUT_DIR
        older = output_dir / "contacts_Acme.xlsx"
        newer = output_dir / "contacts_Beta.xlsx"
        older.write_bytes(b"a")
        newer.write_bytes(b"bb")
        (output_dir / "~$contacts_Acme.xlsx").write_bytes(b"lock file")
        (output_dir / "notes.txt").write_text("ignored", encoding="utf-8")
        now = time.time()
        os.utime(older, (now - 600, now - 600))
        os.utime(newer, (now, now))

        result = await linkedin_router.linkedin_files()

        assert [entry["filename"] for entry in result["files"]] == ["contacts_Beta.xlsx", "contacts_Acme.xlsx"]
        assert result["files"][0] == {
            "filename": "contacts_Beta.xlsx",
            "size_bytes": 2,
            "mtime": pytest.approx(newer.stat().st_mtime),
            "download_url": "/linkedin/download/contacts_Beta.xlsx",
        }
        assert result["files"][1]["size_bytes"] == 1

    @pytest.mark.asyncio
    async def test_download_returns_the_file_and_sanitizes_the_name(self, runtime_dirs):
        target = config.LINKEDIN_OUTPUT_DIR / "contacts_Acme.xlsx"
        target.write_bytes(b"xlsx-bytes")

        response = await linkedin_router.linkedin_download_file("contacts_Acme.xlsx")

        assert isinstance(response, FileResponse)
        assert Path(response.path) == target
        assert response.filename == "contacts_Acme.xlsx"
        assert response.media_type == linkedin_router.XLSX_MEDIA_TYPE

        traversed = await linkedin_router.linkedin_download_file("../contacts_Acme.xlsx")
        assert Path(traversed.path) == target

    @pytest.mark.asyncio
    async def test_download_missing_file_raises_404(self, runtime_dirs):
        with pytest.raises(HTTPException) as exc_info:
            await linkedin_router.linkedin_download_file("nope.xlsx")

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "File 'nope.xlsx' not found"

    @pytest.mark.asyncio
    async def test_decision_makers_endpoint_wraps_the_parser_output(self, monkeypatch):
        monkeypatch.setattr(linkedin_router, "get_all_decision_makers", lambda: [{"id": "dm-1", "name": "Jane Doe"}])

        assert await linkedin_router.get_decision_makers() == {
            "decision_makers": [{"id": "dm-1", "name": "Jane Doe"}],
            "total": 1,
        }

        monkeypatch.setattr(linkedin_router, "get_all_decision_makers", lambda: [])

        assert await linkedin_router.get_decision_makers() == {"decision_makers": [], "total": 0}


# ──────────────────────────────────────────────────────────────────────────────
# Shortlister routes
# ──────────────────────────────────────────────────────────────────────────────
class TestShortlisterRoutes:
    @pytest.mark.asyncio
    async def test_run_rejects_a_second_concurrent_run(self, api_state_reset):
        api_state.shortlister_state.status = "running"
        background = BackgroundTasks()

        with pytest.raises(HTTPException) as exc_info:
            await shortlister_router.run_shortlister(ShortlisterRequest(query="india"), background)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "Shortlister is already running"
        assert background.tasks == []

    @pytest.mark.asyncio
    async def test_run_resets_state_and_starts_a_visualizer_run(self, api_state_reset, monkeypatch, isolated_var):
        api_state.shortlister_state.status = "done"
        api_state.shortlister_state.error = "old error"
        started = {}

        async def fake_begin_run(run_id, log_path):
            started["run_id"] = run_id
            started["log_path"] = log_path

        monkeypatch.setattr(shortlister_router.visualizer_broker, "begin_run", fake_begin_run)
        background = BackgroundTasks()

        result = await shortlister_router.run_shortlister(ShortlisterRequest(query="indian it companies"), background)

        assert result["status"] == "started"
        run_id = result["run_id"]
        assert re.fullmatch(r"session-\d{8}-\d{6}-[0-9a-f]{6}", run_id)
        assert started == {"run_id": run_id, "log_path": config.LOGS_DIR / f"run_{run_id}.jsonl"}
        assert api_state.shortlister_state.status == "idle"
        assert api_state.shortlister_state.error is None

        assert len(background.tasks) == 1
        task = background.tasks[0]
        assert task.func is runner_module.run_shortlister_bg
        assert task.args == ("indian it companies", run_id)

    @pytest.mark.asyncio
    async def test_status_reports_the_exact_payload(self, api_state_reset):
        api_state.shortlister_state.status = "done"
        api_state.shortlister_state.last_excel = "C:/tmp/report.xlsx"
        api_state.shortlister_state.companies = [{"company_name": "Acme Corp"}]
        api_state.shortlister_state.error = None

        assert await shortlister_router.shortlister_status() == {
            "status": "done",
            "excel_path": "C:/tmp/report.xlsx",
            "companies": [{"company_name": "Acme Corp"}],
            "error": None,
        }

    @pytest.mark.asyncio
    async def test_stream_returns_an_event_source_response(self, api_state_reset):
        response = await shortlister_router.shortlister_stream(FakeRequest())

        assert isinstance(response, EventSourceResponse)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_download_requires_an_existing_excel(self, api_state_reset, runtime_dirs):
        api_state.shortlister_state.last_excel = None

        with pytest.raises(HTTPException) as exc_info:
            await shortlister_router.shortlister_download()

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "No Excel file available yet"

        missing = config.SHORTLISTER_OUTPUT_DIR / "report_consolidated_missing.xlsx"
        api_state.shortlister_state.last_excel = str(missing)

        with pytest.raises(HTTPException) as missing_exc:
            await shortlister_router.shortlister_download()

        assert missing_exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_download_serves_the_recorded_excel(self, api_state_reset, runtime_dirs):
        report = config.SHORTLISTER_OUTPUT_DIR / "report_consolidated_2024.xlsx"
        report.write_bytes(b"report-bytes")
        api_state.shortlister_state.last_excel = str(report)

        response = await shortlister_router.shortlister_download()

        assert isinstance(response, FileResponse)
        assert Path(response.path) == report
        assert response.filename == "report_consolidated_2024.xlsx"


# ──────────────────────────────────────────────────────────────────────────────
# Hunter routes
# ──────────────────────────────────────────────────────────────────────────────
class TestHunterRoutes:
    @pytest.mark.asyncio
    async def test_find_email_rejects_a_blank_linkedin_url(self):
        for blank in ("", "   "):
            with pytest.raises(HTTPException) as exc_info:
                await hunter_router.hunter_find_email(HunterEmailRequest(linkedin_url=blank))

            assert exc_info.value.status_code == 400
            assert exc_info.value.detail == "LinkedIn URL or handle is required"

    @pytest.mark.asyncio
    async def test_find_email_delegates_to_hunter_with_stripped_input(self, monkeypatch):
        calls = []
        payload = {"data": {"email": "jane@acme.com", "score": 95}}

        def fake_find_email_by_linkedin(**kwargs):
            calls.append(kwargs)
            return payload

        monkeypatch.setattr(hunter_router, "find_email_by_linkedin", fake_find_email_by_linkedin)

        request = HunterEmailRequest(
            linkedin_url="  https://linkedin.com/in/janedoe  ",
            first_name="Jane",
            last_name="Doe",
            full_name="Jane Doe",
            domain="acme.com",
            company="Acme Corp",
        )

        assert await hunter_router.hunter_find_email(request) == payload
        assert calls == [
            {
                "linkedin_input": "https://linkedin.com/in/janedoe",
                "first_name": "Jane",
                "last_name": "Doe",
                "full_name": "Jane Doe",
                "domain": "acme.com",
                "company": "Acme Corp",
            }
        ]

    @pytest.mark.asyncio
    async def test_find_email_maps_value_error_to_400_and_others_to_500(self, monkeypatch):
        def raising(error):
            def _raise(**kwargs):
                raise error

            return _raise

        monkeypatch.setattr(hunter_router, "find_email_by_linkedin", raising(ValueError("bad handle")))
        with pytest.raises(HTTPException) as value_exc:
            await hunter_router.hunter_find_email(HunterEmailRequest(linkedin_url="handle"))

        assert value_exc.value.status_code == 400
        assert value_exc.value.detail == "bad handle"

        monkeypatch.setattr(hunter_router, "find_email_by_linkedin", raising(RuntimeError("hunter exploded")))
        with pytest.raises(HTTPException) as runtime_exc:
            await hunter_router.hunter_find_email(HunterEmailRequest(linkedin_url="handle"))

        assert runtime_exc.value.status_code == 500
        assert runtime_exc.value.detail == "Hunter API error: hunter exploded"

    @pytest.mark.asyncio
    async def test_email_count_endpoint_returns_the_domain_and_count(self, monkeypatch):
        seen = []

        def fake_count(domain):
            seen.append(domain)
            return 42

        monkeypatch.setattr(hunter_router, "hunter_email_count", fake_count)

        assert await hunter_router.hunter_email_count_endpoint("acme.com") == {"domain": "acme.com", "count": 42}
        assert seen == ["acme.com"]

    @pytest.mark.asyncio
    async def test_store_email_rejects_blanks_and_stores_trimmed_keys(self, api_state_reset):
        with pytest.raises(HTTPException) as exc_info:
            await hunter_router.store_email(StoreEmailRequest(company_name="Acme", dm_name="Jane", email="   "))

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "email must not be empty"

        stored = await hunter_router.store_email(
            StoreEmailRequest(company_name="  Acme Corp ", dm_name=" Jane Doe ", email=" jane@acme.com ")
        )

        assert stored == {"stored": True, "key": "  Acme Corp  /  Jane Doe "}
        assert api_state._email_store == {("acme corp", "jane doe"): "jane@acme.com"}

    @pytest.mark.asyncio
    async def test_smart_enrich_groups_skips_caps_and_reports_metadata(self, monkeypatch, api_state_reset):
        counts = {"acme.com": 12, "zero.com": 0, "cap.com": 30, "boom.com": 4}
        emails = {
            "Jane Doe": "jane@acme.com",
            "Joe Roe": "joe@acme.com",
            "Cap One": "one@cap.com",
            "Cap Two": "two@cap.com",
            "Cap Three": "three@cap.com",
            "Cap Four": "four@cap.com",
            "Explode": RuntimeError("hunter blew up"),
        }

        def fake_email_count(domain):
            return counts.get(domain, 0)

        def fake_find_email_by_linkedin(**kwargs):
            match = emails.get(kwargs.get("full_name"))
            if isinstance(match, Exception):
                raise match
            if match is None:
                return {"data": None}
            return {"data": {"email": match, "score": 90}}

        monkeypatch.setattr(hunter_router, "hunter_email_count", fake_email_count)
        monkeypatch.setattr(hunter_router, "find_email_by_linkedin", fake_find_email_by_linkedin)

        request = HunterSmartEnrichRequest(
            decision_makers=[
                {
                    "id": "dm-1",
                    "name": "Jane Doe",
                    "linkedin_url": "https://linkedin.com/in/janedoe",
                    "company_name": "Acme Corp",
                    "company_website": "https://acme.com",
                },
                {
                    "id": "dm-2",
                    "name": "Joe Roe",
                    "linkedin_url": "https://linkedin.com/in/joeroe",
                    "company_name": "Acme Corp",
                    "company_website": "https://acme.com/about",
                },
                {
                    "id": "dm-3",
                    "name": "No LinkedIn",
                    "company_name": "Acme Corp",
                    "company_website": "https://acme.com",
                },
                {
                    "id": "dm-4",
                    "name": "Skipped Person",
                    "linkedin_url": "https://linkedin.com/in/skipped",
                    "company_name": "Zero Co",
                    "company_website": "https://zero.com",
                },
                {
                    "id": "dm-5",
                    "name": "Cap One",
                    "linkedin_url": "https://linkedin.com/in/capone",
                    "company_name": "Cap Co",
                    "company_website": "https://cap.com",
                },
                {
                    "id": "dm-6",
                    "name": "Cap Two",
                    "linkedin_url": "https://linkedin.com/in/captwo",
                    "company_name": "Cap Co",
                    "company_website": "https://cap.com",
                },
                {
                    "id": "dm-7",
                    "name": "Cap Three",
                    "linkedin_url": "https://linkedin.com/in/capthree",
                    "company_name": "Cap Co",
                    "company_website": "https://cap.com",
                },
                {
                    "id": "dm-8",
                    "name": "Cap Four",
                    "linkedin_url": "https://linkedin.com/in/capfour",
                    "company_name": "Cap Co",
                    "company_website": "https://cap.com",
                },
                {
                    "id": "dm-9",
                    "name": "Explode",
                    "linkedin_url": "https://linkedin.com/in/explode",
                    "company_name": "Boom Co",
                    "company_website": "https://boom.com",
                },
                {
                    "id": "dm-10",
                    "name": "No Email Person",
                    "linkedin_url": "https://linkedin.com/in/noemail",
                    "company_name": "Boom Co",
                    "company_website": "https://boom.com",
                },
            ]
        )

        result = await hunter_router.hunter_smart_enrich(request)

        assert [entry["id"] for entry in result["enriched"]] == ["dm-1", "dm-2", "dm-5", "dm-6", "dm-7"]
        assert result["enriched"][0] == {
            "id": "dm-1",
            "email": "jane@acme.com",
            "score": 90,
            "raw": {"data": {"email": "jane@acme.com", "score": 90}},
        }
        assert result["no_indexed_dm_ids"] == ["dm-4"]
        assert result["skipped_companies"] == ["Zero Co"]
        assert result["stopped_at_cap_companies"] == ["Cap Co"]
        assert result["total_emails_found"] == 5


# ──────────────────────────────────────────────────────────────────────────────
# Export routes
# ──────────────────────────────────────────────────────────────────────────────
class TestExportRoutes:
    @pytest.mark.asyncio
    async def test_list_exports_returns_empty_when_the_dir_is_missing(self, isolated_var):
        assert config.EXPORTS_DIR.exists() is False

        assert await exports_router.list_exports() == {"files": []}

    @pytest.mark.asyncio
    async def test_list_exports_returns_sorted_metadata(self, runtime_dirs):
        export = config.EXPORTS_DIR / "export_2024-05-01_10-00-00.xlsx"
        export.write_bytes(b"xy")
        (config.EXPORTS_DIR / "not_an_export.xlsx").write_bytes(b"x")
        (config.EXPORTS_DIR / "~$export_2024-05-01_10-00-00.xlsx").write_bytes(b"x")

        result = await exports_router.list_exports()

        assert [entry["filename"] for entry in result["files"]] == ["export_2024-05-01_10-00-00.xlsx"]
        assert result["files"][0] == {
            "filename": "export_2024-05-01_10-00-00.xlsx",
            "size_bytes": 2,
            "mtime": pytest.approx(export.stat().st_mtime),
            "download_url": "/export/download/export_2024-05-01_10-00-00.xlsx",
        }

    @pytest.mark.asyncio
    async def test_download_export_404s_and_then_serves_the_file(self, runtime_dirs):
        with pytest.raises(HTTPException) as exc_info:
            await exports_router.download_export("missing.xlsx")

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Export 'missing.xlsx' not found"

        export = config.EXPORTS_DIR / "export_2024-05-01_10-00-00.xlsx"
        export.write_bytes(b"bytes")

        response = await exports_router.download_export("export_2024-05-01_10-00-00.xlsx")

        assert isinstance(response, FileResponse)
        assert Path(response.path) == export
        assert response.media_type == exports_router.XLSX_MEDIA_TYPE

    @pytest.mark.asyncio
    async def test_consolidated_export_streams_the_workbook_and_saves_a_copy(
        self, api_state_reset, runtime_dirs, monkeypatch
    ):
        api_state.shortlister_state.companies = [{"company_name": "Acme Corp"}]
        api_state.shortlister_state.extracted_location = "India"
        api_state._email_store[("acme corp", "jane doe")] = "jane@acme.com"
        monkeypatch.setattr(exports_router, "get_all_decision_makers", lambda: [{"id": "dm-1"}])

        calls = []

        def fake_build_export_xlsx(companies, location, decision_makers, email_store):
            calls.append((companies, location, decision_makers, email_store))
            return b"xlsx-payload"

        monkeypatch.setattr(exports_router, "build_export_xlsx", fake_build_export_xlsx)

        response = await exports_router.export_consolidated()

        assert isinstance(response, StreamingResponse)
        assert response.media_type == exports_router.XLSX_MEDIA_TYPE
        disposition = response.headers["content-disposition"]
        assert re.fullmatch(r'attachment; filename="export_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.xlsx"', disposition)

        assert calls == [
            (
                [{"company_name": "Acme Corp"}],
                "India",
                [{"id": "dm-1"}],
                {("acme corp", "jane doe"): "jane@acme.com"},
            )
        ]

        saved = list(config.EXPORTS_DIR.glob("export_*.xlsx"))
        assert len(saved) == 1
        assert saved[0].read_bytes() == b"xlsx-payload"
        assert disposition.endswith(f'filename="{saved[0].name}"')

    @pytest.mark.asyncio
    async def test_consolidated_export_survives_a_disk_write_failure(
        self, api_state_reset, runtime_dirs, monkeypatch
    ):
        def exploding_write_bytes(self, data):
            raise OSError("read-only filesystem")

        monkeypatch.setattr(exports_router, "get_all_decision_makers", lambda: [])
        monkeypatch.setattr(exports_router, "build_export_xlsx", lambda *args, **kwargs: b"payload")
        monkeypatch.setattr(Path, "write_bytes", exploding_write_bytes)

        response = await exports_router.export_consolidated()

        assert isinstance(response, StreamingResponse)
        assert list(config.EXPORTS_DIR.glob("export_*.xlsx")) == []

    @pytest.mark.asyncio
    async def test_consolidated_export_maps_failures_to_500(self, api_state_reset, runtime_dirs, monkeypatch):
        def exploding_build(*args, **kwargs):
            raise RuntimeError("openpyxl exploded")

        monkeypatch.setattr(exports_router, "get_all_decision_makers", lambda: [])
        monkeypatch.setattr(exports_router, "build_export_xlsx", exploding_build)

        with pytest.raises(HTTPException) as exc_info:
            await exports_router.export_consolidated()

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Export generation failed: openpyxl exploded"
