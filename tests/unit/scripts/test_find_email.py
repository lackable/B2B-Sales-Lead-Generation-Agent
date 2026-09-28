"""Unit tests for ``scripts/find_email.py`` — the Hunter.io LinkedIn CLI."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "find_email.py"
_spec = importlib.util.spec_from_file_location("leadgen_cli_find_email", _SCRIPT_PATH)
find_email = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(find_email)


# ── format_result ──────────────────────────────────────────────────────────────

def test_format_result_data_branch_with_sources():
    result = {
        "data": {
            "email": "jane@acme.com",
            "score": 95,
            "first_name": "Jane",
            "last_name": "Doe",
            "position": "CEO",
            "company": "Acme",
            "domain": "acme.com",
            "verification": {"status": "valid"},
            "sources": [
                {"uri": "u1", "last_seen_on": "2020"},
                {"uri": "u2", "last_seen_on": "2021"},
                {"uri": "u3", "last_seen_on": "2022"},
                {"uri": "u4", "last_seen_on": "2023"},
            ],
            "linkedin_url": "https://linkedin.com/in/jane",
        }
    }
    expected = "\n".join([
        "=" * 50,
        " HUNTER.IO EMAIL FINDER RESULT",
        "=" * 50,
        "Full Name    : Jane Doe",
        " Found Email  : jane@acme.com",
        " Confidence   : 95%",
        " Verification : valid",
        " Position     : CEO",
        " Company      : Acme (acme.com)",
        " LinkedIn URL : https://linkedin.com/in/jane",
        " Sources Count: 4",
        "\n Top Sources:",
        "  - u1 (seen: 2020)",
        "  - u2 (seen: 2021)",
        "  - u3 (seen: 2022)",
        "=" * 50,
    ])
    assert find_email.format_result(result) == expected


def test_format_result_data_branch_without_sources_or_values():
    result = {"data": {"email": None, "score": None}}
    out = find_email.format_result(result)
    assert "Full Name    :" in out
    assert " Found Email  : No email found" in out
    assert " Confidence   : N/A" in out
    assert " Verification : N/A" in out
    assert " Position     : N/A" in out
    assert " Company      : N/A (N/A)" in out
    assert " LinkedIn URL : N/A" in out
    assert " Sources Count: 0" in out
    assert "Top Sources" not in out


def test_format_result_errors_branch():
    result = {"errors": [{"details": "Bad request"}, {"id": "missing_key"}]}
    assert find_email.format_result(result) == "API Error Response:\n- Bad request\n- missing_key"


def test_format_result_fallback_json_branch():
    result = {"foo": "bar"}
    assert find_email.format_result(result) == json.dumps({"foo": "bar"}, indent=2)


# ── main ───────────────────────────────────────────────────────────────────────

def test_main_success_prints_formatted_block(monkeypatch, capsys):
    payload = {"data": {"email": "jane@acme.com", "score": 90, "first_name": "Jane", "last_name": "Doe"}}
    monkeypatch.setattr(find_email, "get_hunter_api_key", lambda provided=None: "key")
    monkeypatch.setattr(find_email, "find_email_by_linkedin", lambda **kwargs: payload)
    monkeypatch.setattr(sys, "argv", ["find_email.py", "-l", "https://linkedin.com/in/jane"])

    find_email.main()

    out = capsys.readouterr().out
    assert out.strip() == find_email.format_result(payload)


def test_main_json_flag_prints_raw_json(monkeypatch, capsys):
    payload = {"data": {"email": "jane@acme.com", "score": 90}}
    monkeypatch.setattr(find_email, "get_hunter_api_key", lambda provided=None: "key")
    monkeypatch.setattr(find_email, "find_email_by_linkedin", lambda **kwargs: payload)
    monkeypatch.setattr(sys, "argv", ["find_email.py", "-l", "handle", "--json"])

    find_email.main()

    assert json.loads(capsys.readouterr().out) == payload


def test_main_missing_key_exits_with_guidance(monkeypatch, capsys):
    monkeypatch.setattr(find_email, "get_hunter_api_key", lambda provided=None: None)
    monkeypatch.setattr(sys, "argv", ["find_email.py", "-l", "handle"])

    with pytest.raises(SystemExit) as excinfo:
        find_email.main()

    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "Error: Hunter.io API key not found." in err
    assert "Please add HUNTER_API_KEY=your_key to the .env file in the repo root," in err


def test_main_client_error_exits(monkeypatch, capsys):
    def boom(**kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(find_email, "get_hunter_api_key", lambda provided=None: "key")
    monkeypatch.setattr(find_email, "find_email_by_linkedin", boom)
    monkeypatch.setattr(sys, "argv", ["find_email.py", "-l", "handle"])

    with pytest.raises(SystemExit) as excinfo:
        find_email.main()

    assert excinfo.value.code == 1
    assert "Error executing Email Finder request: kaboom" in capsys.readouterr().err
