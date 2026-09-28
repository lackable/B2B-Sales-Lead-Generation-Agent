"""Shared fixtures for the leadgen test suite.

Every test must be hermetic: no network, no writes into the real ``var/``
directory, and no leakage of the API's module-level singletons.
"""

import pytest

from leadgen import config
from leadgen.api import state as api_state


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
    }
    for name, value in {**path_settings, **string_settings}.items():
        monkeypatch.setattr(config, name, value)

    return tmp_path


@pytest.fixture
def api_state_reset():
    """Reset the API singletons (agent states, email store, WS clients) around a test."""
    api_state.shortlister_state.reset()
    api_state.linkedin_state.reset()
    api_state._email_store.clear()
    api_state.ws_log_clients.clear()
    yield
    api_state.shortlister_state.reset()
    api_state.linkedin_state.reset()
    api_state._email_store.clear()
    api_state.ws_log_clients.clear()
