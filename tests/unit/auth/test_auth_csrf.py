"""Origin parsing and the CSRF middleware."""

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from leadgen.auth.csrf import OriginCheckMiddleware, origin_is_allowed


async def _ok(_request):
    return JSONResponse({"ok": True})


def _csrf_app() -> Starlette:
    app = Starlette(routes=[Route("/write", _ok, methods=["POST", "GET"])])
    app.add_middleware(OriginCheckMiddleware)
    return app


def test_missing_or_null_origin_is_allowed():
    assert origin_is_allowed(None) is True
    assert origin_is_allowed("") is True
    assert origin_is_allowed("null") is True


def test_configured_origins_are_allowed_with_normalization():
    for origin in ("http://localhost:5173", "HTTP://LOCALHOST:5173", "http://localhost:5173/"):
        assert origin_is_allowed(origin, ["http://localhost:5173"]) is True


def test_foreign_origins_are_rejected():
    assert origin_is_allowed("http://evil.test", ["http://localhost:5173"]) is False
    assert origin_is_allowed("https://localhost:5173", ["http://localhost:5173"]) is False


def test_defaults_to_the_configured_allow_list(monkeypatch):
    from leadgen import config

    monkeypatch.setattr(config, "CORS_ALLOWED_ORIGINS", ["http://app.example"])

    assert origin_is_allowed("http://app.example") is True
    assert origin_is_allowed("http://localhost:5173") is False


def test_middleware_blocks_unsafe_cross_origin_requests(monkeypatch):
    from leadgen import config

    monkeypatch.setattr(config, "CORS_ALLOWED_ORIGINS", ["http://localhost:5173"])
    client = TestClient(_csrf_app())

    blocked = client.post("/write", headers={"Origin": "http://evil.test"})
    allowed = client.post("/write", headers={"Origin": "http://localhost:5173"})
    no_origin = client.post("/write")
    safe = client.get("/write", headers={"Origin": "http://evil.test"})

    assert blocked.status_code == 403
    assert blocked.json() == {"detail": "Cross-origin request rejected."}
    assert allowed.status_code == 200
    assert no_origin.status_code == 200
    assert safe.status_code == 200


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_every_unsafe_method_is_checked(monkeypatch, method):
    from leadgen import config

    monkeypatch.setattr(config, "CORS_ALLOWED_ORIGINS", ["http://localhost:5173"])
    app = Starlette(routes=[Route("/write", _ok, methods=["POST", "PUT", "PATCH", "DELETE"])])
    app.add_middleware(OriginCheckMiddleware)

    response = TestClient(app).request(method, "/write", headers={"Origin": "http://evil.test"})

    assert response.status_code == 403
