"""Argon2id password hashing and the password policy."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from leadgen import config
from leadgen.auth.errors import ValidationFailed

PASSWORD_MAX_LENGTH = 128

_hasher = PasswordHasher()

# Verified against when the username is unknown, so a failed login costs the
# same CPU time whether or not the account exists.
_DUMMY_PASSWORD = "timing-safety-dummy-password"
_DUMMY_HASH = _hasher.hash(_DUMMY_PASSWORD)


def hash_password(password: str) -> str:
    """Hash with argon2id using the library defaults (t=3, m=64 MiB, p=4)."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verification; any malformed hash counts as a mismatch."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash uses outdated argon2 parameters."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def dummy_verify() -> None:
    """Burn one verification's worth of time for unknown usernames."""
    verify_password(_DUMMY_PASSWORD, _DUMMY_HASH)


def validate_password(password: str, *, username: str) -> None:
    """Enforce the password policy, raising ``ValidationFailed`` on violation."""
    candidate = password or ""
    if len(candidate) < config.PASSWORD_MIN_LENGTH:
        raise ValidationFailed(f"Passwords must be at least {config.PASSWORD_MIN_LENGTH} characters long.")
    if len(candidate) > PASSWORD_MAX_LENGTH:
        raise ValidationFailed(f"Passwords must be at most {PASSWORD_MAX_LENGTH} characters long.")
    if not candidate.strip():
        raise ValidationFailed("Passwords cannot be only whitespace.")
    if username and candidate.casefold() == username.casefold():
        raise ValidationFailed("Passwords cannot be the same as the username.")
