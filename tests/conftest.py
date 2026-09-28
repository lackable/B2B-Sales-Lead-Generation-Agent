"""Shared fixtures for the leadgen test suite.

Every test must be hermetic: no network, no writes into the real ``var/``
directory, and no leakage of the API's module-level singletons.
"""

import pytest
from starlette.testclient import TestClient

from leadgen import config
from leadgen.api import state as api_state
from leadgen.api.app import app
from leadgen.auth import rate_limit
from leadgen.db import engine as db_engine
from leadgen.db import migrate
from leadgen.db.session import get_session_factory

# Credentials for the account the API fixtures create.
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "correct-horse-battery"


@pytest.fixture
def isolated_var(tmp_path, monkeypatch):
    """Point every runtime artifact path at a tmp dir instead of ``var/``."""
    runs = tmp_path / "runs"

    path_settings = {
        "VAR_DIR": tmp_path,
        "DATA_DIR": tmp_path / "data",
        "RUNS_DIR": runs,
        "EXPORTS_DIR": tmp_path / "exports",
        "LOGS_DIR": tmp_path / "logs",
        "SHORTLISTER_OUTPUT_DIR": runs / "shortlister",
        "SHORTLISTER_REPORTS_DIR": runs / "shortlister" / "reports",
        "LINKEDIN_OUTPUT_DIR": runs / "linkedin",
    }
    string_settings = {
        "MEMORY_DB_PATH": str(tmp_path / "data" / "shortlister.db"),
        "LINKEDIN_MEMORY_DB_PATH": str(tmp_path / "data" / "linkedin.db"),
        "EXCEL_OUTPUT_DIR": str(runs / "shortlister"),
        "REPORTS_OUTPUT_DIR": str(runs / "shortlister" / "reports"),
        "OUTPUT_DIR": str(runs / "linkedin"),
        "LOG_DIR": str(tmp_path / "logs"),
        "APP_DB_URL": f"sqlite:///{(tmp_path / 'data' / 'app.db').as_posix()}",
    }
    for name, value in {**path_settings, **string_settings}.items():
        monkeypatch.setattr(config, name, value)

    # The engine cache is keyed by URL, but drop it so no handle outlives the test.
    db_engine.dispose_engine()
    yield tmp_path
    db_engine.dispose_engine()


@pytest.fixture
def auth_db(isolated_var):
    """A fresh, migrated auth database inside the temp var dir."""
    db_engine.dispose_engine()
    migrate.upgrade_database()
    return isolated_var


@pytest.fixture
def db_session(auth_db):
    """A session over the temp database; rolled back and closed afterwards."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def api_state_reset():
    """Reset the API singletons (agent states, email store, WS clients) around a test."""
    api_state.shortlister_state.reset()
    api_state.linkedin_state.reset()
    api_state._email_store.clear()
    api_state.ws_log_clients.clear()
    rate_limit.reset_limits()
    yield
    api_state.shortlister_state.reset()
    api_state.linkedin_state.reset()
    api_state._email_store.clear()
    api_state.ws_log_clients.clear()
    rate_limit.reset_limits()


@pytest.fixture
def authed_client(auth_db, api_state_reset):
    """A ``TestClient`` with the first-run setup already done, logged in as the admin."""
    with TestClient(app) as client:
        response = client.post(
            "/auth/setup",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 200, response.text
        yield client
