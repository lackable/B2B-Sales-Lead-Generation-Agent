"""HTTP behaviour of ``/auth/*``: cookies, guards, CSRF and the WebSocket handshake."""

import re

import pytest
from sqlalchemy import select
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from leadgen import config
from leadgen.api.app import app
from leadgen.api.state import ws_log_clients
from leadgen.auth import rate_limit
from leadgen.db.models import ROLE_ADMIN, AuthSession
from leadgen.db.session import get_session_factory

ADMIN_USERNAME = "AdminUser"
ADMIN_PASSWORD = "correct-horse-battery"
NEW_PASSWORD = "a-brand-new-secret"

# Everything else in the OpenAPI surface must reject anonymous callers.
PUBLIC_ROUTES = {
    ("GET", "/health"),
    ("GET", "/auth/setup-status"),
    ("POST", "/auth/setup"),
    ("POST", "/auth/login"),
    ("POST", "/auth/password/reset"),
}

HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


@pytest.fixture
def client(auth_db, api_state_reset):
    """A TestClient with migrations applied and no account created yet."""
    with TestClient(app) as test_client:
        yield test_client


def _setup(client, username=ADMIN_USERNAME, password=ADMIN_PASSWORD):
    response = client.post("/auth/setup", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def _create_user(client, username="newbie", role="user"):
    response = client.post("/admin/users", json={"username": username, "role": role})
    assert response.status_code == 201, response.text
    return response.json()


# ── public surface ─────────────────────────────────────────────────────────────


def test_health_and_setup_status_are_public(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/auth/setup-status").json() == {"needs_setup": True}


def test_setup_status_flips_after_setup(client):
    _setup(client)

    assert client.get("/auth/setup-status").json() == {"needs_setup": False}


def _openapi_surface() -> set:
    return {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method.upper() in HTTP_METHODS
    }


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "placeholder", path)


def test_every_non_public_route_rejects_anonymous_callers(client):
    """A new endpoint that forgets the auth dependency fails here."""
    guarded = sorted(_openapi_surface() - PUBLIC_ROUTES)
    assert len(guarded) > 20  # sanity: the surface really was enumerated

    for method, path in guarded:
        url = _concrete(path)
        response = client.request(method, url, json={})

        assert response.status_code == 401, f"{method} {url} returned {response.status_code}"
        assert response.json() == {"detail": "Authentication required."}, f"{method} {url}"


def test_the_public_routes_are_reachable_without_a_session(client):
    for method, path in sorted(PUBLIC_ROUTES):
        response = client.request(method, path, json={})

        assert response.status_code != 401, f"{method} {path} required a session"


# ── setup ──────────────────────────────────────────────────────────────────────


def test_setup_creates_an_admin_and_returns_the_recovery_code(client):
    body = _setup(client)

    assert body["user"]["username"] == ADMIN_USERNAME
    assert body["user"]["role"] == ROLE_ADMIN
    assert body["user"]["is_active"] is True
    assert body["user"]["must_change_password"] is False
    assert body["user"]["last_login_at"] is None
    assert body["user"]["created_at"]
    assert body["recovery_code"].count("-") == 4
    assert client.get("/auth/me").json()["username"] == ADMIN_USERNAME


def test_setup_sets_a_locked_down_session_cookie(client):
    response = client.post("/auth/setup", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})

    header = response.headers["set-cookie"].lower()
    assert header.startswith(config.SESSION_COOKIE_NAME)
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "path=/" in header
    assert "max-age=" in header
    assert "secure" not in header


def test_secure_cookie_flag_follows_the_setting(client, monkeypatch):
    monkeypatch.setattr(config, "COOKIE_SECURE", True)

    response = client.post("/auth/setup", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})

    assert "secure" in response.headers["set-cookie"].lower()


def test_the_session_token_is_never_stored_in_plain_text(client):
    _setup(client)
    token = client.cookies.get(config.SESSION_COOKIE_NAME)

    with get_session_factory()() as db:
        stored = [row.token_hash for row in db.scalars(select(AuthSession)).all()]

    assert len(stored) == 1
    assert token not in stored
    assert len(stored[0]) == 64


def test_setup_can_only_run_once(client):
    _setup(client)

    second = client.post("/auth/setup", json={"username": "someone-else", "password": ADMIN_PASSWORD})

    assert second.status_code == 409
    assert second.json() == {"detail": "Setup has already been completed."}


def test_setup_rejects_invalid_input(client):
    bad_username = client.post("/auth/setup", json={"username": "a b", "password": ADMIN_PASSWORD})
    bad_password = client.post("/auth/setup", json={"username": ADMIN_USERNAME, "password": "short"})

    assert bad_username.status_code == 400
    assert bad_password.status_code == 400
    assert client.get("/auth/setup-status").json() == {"needs_setup": True}


def test_setup_is_rate_limited_per_client(client):
    for _ in range(rate_limit.SETUP_IP_LIMIT[0]):
        client.post("/auth/setup", json={"username": "a b", "password": ADMIN_PASSWORD})

    blocked = client.post("/auth/setup", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})

    assert blocked.status_code == 429


# ── login / logout ─────────────────────────────────────────────────────────────


def test_login_sets_a_new_cookie_and_returns_the_user(client):
    _setup(client)
    client.cookies.clear()

    response = client.post("/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})

    assert response.status_code == 200
    assert response.json()["username"] == ADMIN_USERNAME
    assert client.cookies.get(config.SESSION_COOKIE_NAME)


def test_login_is_case_insensitive(client):
    _setup(client)
    client.cookies.clear()

    response = client.post("/auth/login", json={"username": ADMIN_USERNAME.upper(), "password": ADMIN_PASSWORD})

    assert response.status_code == 200
    assert response.json()["username"] == ADMIN_USERNAME


def test_login_failure_is_generic_and_leaves_no_cookie(client):
    _setup(client)
    client.cookies.clear()

    wrong_password = client.post("/auth/login", json={"username": ADMIN_USERNAME, "password": "not-the-password"})
    unknown_user = client.post("/auth/login", json={"username": "ghost", "password": ADMIN_PASSWORD})

    assert wrong_password.status_code == 401
    assert unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json() == {"detail": "Invalid username or password."}
    assert config.SESSION_COOKIE_NAME not in client.cookies


def test_login_locks_the_account_after_repeated_failures(client, monkeypatch):
    monkeypatch.setattr(config, "AUTH_MAX_FAILED_LOGINS", 2)
    _setup(client)
    client.cookies.clear()

    for _ in range(2):
        client.post("/auth/login", json={"username": ADMIN_USERNAME, "password": "not-the-password"})
    locked = client.post("/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})

    assert locked.status_code == 403
    assert "locked" in locked.json()["detail"]


def test_login_rejects_a_disabled_account(client):
    _setup(client)
    created = _create_user(client, "blocked")

    client.patch(f"/admin/users/{created['user']['id']}", json={"is_active": False})
    client.cookies.clear()

    response = client.post("/auth/login", json={"username": "blocked", "password": created["temporary_password"]})

    assert response.status_code == 403
    assert response.json() == {"detail": "This account has been disabled."}


def test_login_is_rate_limited_per_client(client):
    _setup(client)
    client.cookies.clear()

    for _ in range(rate_limit.LOGIN_IP_LIMIT[0]):
        client.post("/auth/login", json={"username": ADMIN_USERNAME, "password": "not-the-password"})

    blocked = client.post("/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})

    assert blocked.status_code == 429


def test_logout_revokes_the_session_and_clears_the_cookie(client):
    _setup(client)

    response = client.post("/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"status": "logged_out"}
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert client.get("/auth/me").status_code == 401

    with get_session_factory()() as db:
        rows = db.scalars(select(AuthSession)).all()

    assert [row.revoked_reason for row in rows] == ["logout"]


# ── password change / reset ────────────────────────────────────────────────────


def test_me_requires_a_session_only(client):
    assert client.get("/auth/me").status_code == 401
    _setup(client)
    assert client.get("/auth/me").status_code == 200


def test_password_change_requires_the_current_password(client):
    _setup(client)

    response = client.post(
        "/auth/password/change", json={"current_password": "wrong", "new_password": NEW_PASSWORD}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "The current password is incorrect."}


def test_password_change_revokes_other_sessions_and_keeps_this_one(client):
    _setup(client)
    other = TestClient(app)
    other.post("/auth/login", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert other.get("/auth/me").status_code == 200

    response = client.post(
        "/auth/password/change", json={"current_password": ADMIN_PASSWORD, "new_password": NEW_PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["recovery_code"] is None
    assert response.json()["user"]["username"] == ADMIN_USERNAME
    assert client.get("/auth/me").status_code == 200
    assert other.get("/auth/me").status_code == 401
    other.close()


def test_password_change_rejects_policy_violations(client):
    _setup(client)

    response = client.post(
        "/auth/password/change", json={"current_password": ADMIN_PASSWORD, "new_password": "short"}
    )

    assert response.status_code == 400


def test_password_reset_rotates_the_code_and_revokes_all_sessions(client):
    setup_body = _setup(client)

    response = client.post(
        "/auth/password/reset",
        json={
            "username": ADMIN_USERNAME,
            "recovery_code": setup_body["recovery_code"],
            "new_password": NEW_PASSWORD,
        },
    )

    assert response.status_code == 200
    assert response.json()["recovery_code"] != setup_body["recovery_code"]
    assert client.get("/auth/me").status_code == 401

    with get_session_factory()() as db:
        rows = db.scalars(select(AuthSession)).all()
    assert len(rows) == 1
    assert all(row.revoked_at is not None for row in rows)

    client.cookies.clear()
    assert client.post("/auth/login", json={"username": ADMIN_USERNAME, "password": NEW_PASSWORD}).status_code == 200


def test_password_reset_rejects_a_wrong_code(client):
    _setup(client)

    response = client.post(
        "/auth/password/reset",
        json={
            "username": ADMIN_USERNAME,
            "recovery_code": "0000-0000-0000-0000-0000",
            "new_password": NEW_PASSWORD,
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid username or recovery code."}


def test_recovery_code_regeneration_requires_the_password(client):
    _setup(client)

    wrong = client.post("/auth/recovery-code/regenerate", json={"password": "wrong"})
    right = client.post("/auth/recovery-code/regenerate", json={"password": ADMIN_PASSWORD})

    assert wrong.status_code == 401
    assert right.status_code == 200
    assert right.json()["recovery_code"].count("-") == 4


# ── CSRF ───────────────────────────────────────────────────────────────────────


def test_cross_origin_writes_are_rejected(client):
    _setup(client)

    response = client.post("/reset", headers={"Origin": "http://evil.test"})

    assert response.status_code == 403
    assert response.json() == {"detail": "Cross-origin request rejected."}


def test_configured_origin_and_safe_methods_are_allowed(client):
    _setup(client)

    same_origin = client.post("/reset", headers={"Origin": config.CORS_ALLOWED_ORIGINS[0]})
    cross_origin_read = client.get("/auth/me", headers={"Origin": "http://evil.test"})

    assert same_origin.status_code == 200
    assert cross_origin_read.status_code == 200


# ── websockets ─────────────────────────────────────────────────────────────────


def test_websocket_requires_a_session(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/logs") as socket:
            socket.receive_text()

    assert exc.value.code == 1008


def test_websocket_rejects_a_foreign_origin(client):
    _setup(client)

    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/logs", headers={"Origin": "http://evil.test"}) as socket:
            socket.receive_text()

    assert exc.value.code == 1008


def test_websocket_accepts_a_valid_session(client):
    _setup(client)

    with client.websocket_connect("/ws/logs", headers={"Origin": config.CORS_ALLOWED_ORIGINS[0]}) as socket:
        assert socket is not None
        assert len(ws_log_clients) == 1

    assert ws_log_clients == []
