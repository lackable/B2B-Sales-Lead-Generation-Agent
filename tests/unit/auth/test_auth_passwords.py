"""Password hashing, rehash detection and the password policy."""

import pytest

from leadgen import config
from leadgen.auth import passwords
from leadgen.auth.errors import ValidationFailed


def test_hash_is_argon2id_and_verifies():
    digest = passwords.hash_password("correct-horse-battery")

    assert digest.startswith("$argon2id$")
    assert passwords.verify_password("correct-horse-battery", digest) is True


def test_hash_is_salted_per_call():
    assert passwords.hash_password("same-password") != passwords.hash_password("same-password")


def test_verify_rejects_wrong_password_and_garbage_hashes():
    digest = passwords.hash_password("correct-horse-battery")

    assert passwords.verify_password("wrong-password", digest) is False
    assert passwords.verify_password("correct-horse-battery", "not-a-hash") is False
    assert passwords.verify_password("correct-horse-battery", "") is False


def test_needs_rehash_is_false_for_a_fresh_hash_and_true_for_junk():
    assert passwords.needs_rehash(passwords.hash_password("correct-horse-battery")) is False
    assert passwords.needs_rehash("not-a-hash") is True


def test_needs_rehash_detects_outdated_parameters():
    from argon2 import PasswordHasher

    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("correct-horse-battery")

    assert passwords.needs_rehash(weak) is True


def test_dummy_verify_burns_a_verification_without_raising():
    assert passwords.dummy_verify() is None


def test_password_policy_enforces_length_bounds():
    with pytest.raises(ValidationFailed) as too_short:
        passwords.validate_password("short", username="alice")
    assert str(config.PASSWORD_MIN_LENGTH) in str(too_short.value)

    with pytest.raises(ValidationFailed):
        passwords.validate_password("x" * (passwords.PASSWORD_MAX_LENGTH + 1), username="alice")

    passwords.validate_password("a-perfectly-fine-password", username="alice")


def test_password_policy_rejects_whitespace_only():
    with pytest.raises(ValidationFailed):
        passwords.validate_password(" " * 20, username="alice")


def test_password_policy_rejects_the_username_in_any_case():
    for candidate in ("Alice-2026-user", "ALICE-2026-USER"):
        with pytest.raises(ValidationFailed) as exc:
            passwords.validate_password(candidate, username=candidate)
        assert "username" in str(exc.value)


def test_min_length_follows_the_setting(monkeypatch):
    monkeypatch.setattr(config, "PASSWORD_MIN_LENGTH", 4)

    passwords.validate_password("abcd", username="alice")
    with pytest.raises(ValidationFailed):
        passwords.validate_password("abc", username="alice")
