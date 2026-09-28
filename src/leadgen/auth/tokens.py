"""Session tokens: opaque secret in the cookie, sha256 digest in the database."""

import hashlib
import secrets

TOKEN_BYTES = 32


def generate_session_token() -> str:
    """A fresh 256-bit URL-safe token for the session cookie."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Deterministic digest used for lookups — the raw token is never stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
