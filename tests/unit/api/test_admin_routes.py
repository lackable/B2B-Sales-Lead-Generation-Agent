"""HTTP behaviour of ``/admin/users/*``: authorization and the user lifecycle."""

import pytest
from starlette.testclient import TestClient

from leadgen.api.app import app
from leadgen.db.models import ROLE_USER

ADMIN_USERNAME = "AdminUser"
ADMIN_PASSWORD = "correct-horse-battery"
NEW_PASSWORD = "a-brand-new-secret"


@pytest.fixture
def admin_client(auth_db, api_state_reset):
    """A TestClient signed in as the first (admin) account."""
    with TestClient(app) as client:
        response = client.post("/auth/setup", json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
        assert response.status_code == 200, response.text
        yield client


def _create(client, username="newbie", role="user"):
    return client.post("/admin/users", json={"username": username, "role": role})


def _sign_in(username, password):
    """A second client so the admin's own cookie is left alone."""
    client = TestClient(app)
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return client


def test_list_users_starts_with_the_admin(admin_client):
    response = admin_client.get("/admin/users")

    assert response.status_code == 200
    users = response.json()["users"]
    assert [user["username"] for user in users] == [ADMIN_USERNAME]
    assert users[0]["role"] == "admin"


def test_non_admins_get_403(admin_client):
    created = _create(admin_client, "member").json()
    member = _sign_in("member", created["temporary_password"])

    forbidden_list = member.get("/admin/users")
    forbidden_create = member.post("/admin/users", json={"username": "another"})
    not_found = member.patch(f"/admin/users/{created['user']['id']}", json={"is_active": False})

    assert forbidden_list.status_code == 403
    assert forbidden_list.json() == {"detail": "Administrator privileges required."}
    assert forbidden_create.status_code == 403
    assert not_found.status_code == 403
    member.close()


def test_create_user_returns_credentials_and_forces_a_change(admin_client):
    response = _create(admin_client, "Member.One")

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["username"] == "Member.One"
    assert body["user"]["role"] == ROLE_USER
    assert body["user"]["must_change_password"] is True
    assert body["user"]["created_at"]
    assert len(body["temporary_password"]) >= 12
    assert body["recovery_code"].count("-") == 4

    member = _sign_in("member.one", body["temporary_password"])
    assert member.get("/auth/me").json()["must_change_password"] is True

    changed = member.post(
        "/auth/password/change",
        json={"current_password": body["temporary_password"], "new_password": NEW_PASSWORD},
    )

    assert changed.status_code == 200
    new_code = changed.json()["recovery_code"]
    assert new_code and new_code != body["recovery_code"]
    assert member.get("/auth/me").json()["must_change_password"] is False
    member.close()

    re_login = TestClient(app)
    assert re_login.post("/auth/login", json={"username": "member.one", "password": NEW_PASSWORD}).status_code == 200
    re_login.close()


def test_create_user_rejects_duplicates_and_invalid_input(admin_client):
    _create(admin_client, "taken")

    duplicate = _create(admin_client, "TAKEN")
    bad_username = _create(admin_client, "no spaces")
    bad_role = _create(admin_client, "fine-name", role="superuser")

    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "That username is already taken."}
    assert bad_username.status_code == 400
    assert bad_role.status_code == 400


def test_create_user_can_create_another_admin(admin_client):
    created = _create(admin_client, "second-admin", role="admin")

    assert created.status_code == 201
    assert created.json()["user"]["role"] == "admin"

    peer = _sign_in("second-admin", created.json()["temporary_password"])
    assert peer.get("/admin/users").status_code == 200
    peer.close()


def test_update_user_disables_revokes_and_reenables(admin_client):
    created = _create(admin_client, "blocked").json()
    member = _sign_in("blocked", created["temporary_password"])
    assert member.get("/auth/me").status_code == 200

    disabled = admin_client.patch(f"/admin/users/{created['user']['id']}", json={"is_active": False})

    assert disabled.status_code == 200
    assert disabled.json()["is_active"] is False
    assert member.get("/auth/me").status_code == 401
    member.close()

    enabled = admin_client.patch(f"/admin/users/{created['user']['id']}", json={"is_active": True})

    assert enabled.status_code == 200
    assert enabled.json()["is_active"] is True


def test_update_user_changes_the_role(admin_client):
    created = _create(admin_client, "promote-me").json()

    promoted = admin_client.patch(f"/admin/users/{created['user']['id']}", json={"role": "admin"})

    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"

    member = _sign_in("promote-me", created["temporary_password"])
    assert member.get("/admin/users").status_code == 200
    member.close()


def test_update_user_refuses_to_lock_the_last_admin_out(admin_client):
    me = admin_client.get("/auth/me").json()

    disabled = admin_client.patch(f"/admin/users/{me['id']}", json={"is_active": False})
    demoted = admin_client.patch(f"/admin/users/{me['id']}", json={"role": "user"})

    assert disabled.status_code == 400
    assert demoted.status_code == 400
    assert admin_client.get("/auth/me").json()["role"] == "admin"


def test_update_user_requires_a_field_and_a_known_user(admin_client):
    empty = admin_client.patch("/admin/users/whatever", json={})
    missing = admin_client.patch("/admin/users/missing-id", json={"is_active": True})

    assert empty.status_code == 400
    assert missing.status_code == 404
    assert missing.json() == {"detail": "User not found."}


def test_unknown_role_is_rejected(admin_client):
    created = _create(admin_client, "role-test").json()

    response = admin_client.patch(f"/admin/users/{created['user']['id']}", json={"role": "wizard"})

    assert response.status_code == 400


def test_revoke_sessions_forces_every_client_to_log_out(admin_client):
    created = _create(admin_client, "kick-me").json()
    member = _sign_in("kick-me", created["temporary_password"])
    assert member.get("/auth/me").status_code == 200

    response = admin_client.post(f"/admin/users/{created['user']['id']}/revoke-sessions")

    assert response.status_code == 200
    assert response.json() == {"status": "revoked", "revoked_sessions": 1}
    assert member.get("/auth/me").status_code == 401
    member.close()


def test_revoke_sessions_for_an_unknown_user_is_404(admin_client):
    response = admin_client.post("/admin/users/missing-id/revoke-sessions")

    assert response.status_code == 404
