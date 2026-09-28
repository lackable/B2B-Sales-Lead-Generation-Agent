"""Unit tests for leadgen.core.telemetry.redact."""

from leadgen.core.telemetry.redact import redact


def test_redact_replaces_sensitive_top_level_key():
    assert redact({"api_key": "abc", "name": "Ada"}) == {"api_key": "***", "name": "Ada"}


def test_redact_recurses_into_nested_dicts():
    assert redact({"outer": {"api_key": "x", "keep": "y"}}) == {"outer": {"api_key": "***", "keep": "y"}}


def test_redact_recurses_into_lists():
    assert redact([{"token": "t"}, {"safe": 1}, "plain"]) == [{"token": "***"}, {"safe": 1}, "plain"]


def test_redact_matches_all_documented_key_patterns():
    for key in ("api_key", "api-key", "apikey", "TOKEN", "token", "secret", "SECRET", "ApiKey", "My_API_Key"):
        assert redact({key: "value"})[key] == "***", key


def test_redact_is_case_insensitive_and_matches_substrings():
    assert redact({"X-Api-Key": "v"})["X-Api-Key"] == "***"
    assert redact({"access_token_value": "v"})["access_token_value"] == "***"
    assert redact({"clientsecret": "v"})["clientsecret"] == "***"


def test_redact_replaces_container_values_of_sensitive_keys():
    assert redact({"token": {"nested": 1}}) == {"token": "***"}
    assert redact({"secret": [1, 2, 3]}) == {"secret": "***"}


def test_redact_leaves_non_sensitive_keys_untouched():
    assert redact({"name": "Ada", "monkey": "banana", "count": 3}) == {"name": "Ada", "monkey": "banana", "count": 3}


def test_redact_passes_through_non_dict_and_non_list_values():
    for value in ("str", 3, 3.5, None, True):
        assert redact(value) == value
    sentinel = object()
    assert redact(sentinel) is sentinel


def test_redact_returns_copies_not_aliases():
    original = {"nested": {"api_key": "x", "keep": [1, 2]}, "list": [{"secret": "s"}]}
    result = redact(original)
    assert result == {"nested": {"api_key": "***", "keep": [1, 2]}, "list": [{"secret": "***"}]}
    result["nested"]["keep"].append(3)
    result["list"].append("new")
    assert original["nested"]["keep"] == [1, 2]
    assert original["list"] == [{"secret": "s"}]
