"""Unit tests for leadgen.core.telemetry.snapshots."""

from leadgen.core.telemetry.snapshots import sanitize_decision_makers


def test_position_is_preferred_for_role():
    result = sanitize_decision_makers([{"name": "Ada", "position": "CTO", "role": "ignored", "title": "ignored"}])
    assert result == [{"name": "Ada", "role": "CTO"}]


def test_role_is_used_when_position_missing():
    assert sanitize_decision_makers([{"name": "Ada", "role": "VP"}]) == [{"name": "Ada", "role": "VP"}]


def test_title_is_used_when_position_and_role_missing():
    assert sanitize_decision_makers([{"name": "Ada", "title": "Founder"}]) == [{"name": "Ada", "role": "Founder"}]


def test_none_fields_fall_through_to_later_sources():
    assert sanitize_decision_makers([{"name": "A", "position": None, "role": "R", "title": "T"}]) == [
        {"name": "A", "role": "R"}
    ]


def test_empty_position_falls_through_to_title():
    assert sanitize_decision_makers([{"name": "A", "position": "", "title": "T"}]) == [{"name": "A", "role": "T"}]


def test_missing_or_none_fields_become_empty_strings():
    assert sanitize_decision_makers([{}]) == [{"name": "", "role": ""}]
    assert sanitize_decision_makers([{"name": None, "position": None}]) == [{"name": "", "role": ""}]


def test_whitespace_is_stripped():
    assert sanitize_decision_makers([{"name": "  Ada  ", "position": "  CTO  "}]) == [{"name": "Ada", "role": "CTO"}]


def test_urls_and_emails_are_excluded_from_output():
    result = sanitize_decision_makers(
        [{"name": "Ada", "position": "CTO", "linkedin_url": "https://x", "email": "a@b.c", "phone": "1"}]
    )
    assert result == [{"name": "Ada", "role": "CTO"}]
    assert set(result[0]) == {"name", "role"}


def test_empty_input_returns_empty_list():
    assert sanitize_decision_makers([]) == []


def test_multiple_contacts_preserve_order():
    result = sanitize_decision_makers([{"name": "A", "position": "P1"}, {"name": "B", "role": "P2"}])
    assert result == [{"name": "A", "role": "P1"}, {"name": "B", "role": "P2"}]
