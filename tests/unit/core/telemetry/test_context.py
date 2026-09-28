"""Unit tests for leadgen.core.telemetry.context."""

import pytest

from leadgen.core.telemetry import context as context_module
from leadgen.core.telemetry.context import (
    bind_log_context,
    get_log_context,
    push_log_context,
    reset_log_context,
)


@pytest.fixture(autouse=True)
def _isolated_context():
    token = context_module._log_context.set({})
    yield
    context_module._log_context.reset(token)


def test_get_returns_empty_default():
    assert get_log_context() == {}


def test_get_returns_a_copy():
    push_log_context(agent="a")
    snapshot = get_log_context()
    snapshot["agent"] = "mutated"
    assert get_log_context() == {"agent": "a"}


def test_push_merges_fields():
    push_log_context(agent="a")
    push_log_context(run_id="r")
    assert get_log_context() == {"agent": "a", "run_id": "r"}


def test_push_skips_none_values():
    push_log_context(agent="a", run_id=None, company=None)
    assert get_log_context() == {"agent": "a"}


def test_reset_restores_previous_state():
    assert get_log_context() == {}
    token = push_log_context(agent="a")
    assert get_log_context() == {"agent": "a"}
    push_log_context(run_id="r")
    assert get_log_context() == {"agent": "a", "run_id": "r"}
    reset_log_context(token)
    assert get_log_context() == {}


def test_bind_sets_and_restores_context():
    with bind_log_context(company="Acme", execution_id="e1"):
        assert get_log_context() == {"company": "Acme", "execution_id": "e1"}
        with bind_log_context(branch="b1"):
            assert get_log_context() == {"company": "Acme", "execution_id": "e1", "branch": "b1"}
        assert get_log_context() == {"company": "Acme", "execution_id": "e1"}
    assert get_log_context() == {}


def test_bind_restores_context_after_exception():
    with pytest.raises(RuntimeError, match="boom"):
        with bind_log_context(company="Acme"):
            assert get_log_context() == {"company": "Acme"}
            raise RuntimeError("boom")
    assert get_log_context() == {}
