"""Domain exceptions; the API layer maps ``status_code`` onto HTTP responses."""

from typing import Optional


class AuthError(Exception):
    """Base class for every authentication/authorization failure."""

    status_code = 400

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class ValidationFailed(AuthError):
    """A username, password or role did not satisfy the policy."""

    status_code = 400


class InvalidCredentials(AuthError):
    status_code = 401


class InvalidRecoveryCode(AuthError):
    status_code = 400


class AccountLocked(AuthError):
    status_code = 403


class AccountDisabled(AuthError):
    status_code = 403


class NotFound(AuthError):
    status_code = 404


class SetupAlreadyCompleted(AuthError):
    status_code = 409


class UsernameTaken(AuthError):
    status_code = 409


class RateLimited(AuthError):
    status_code = 429
