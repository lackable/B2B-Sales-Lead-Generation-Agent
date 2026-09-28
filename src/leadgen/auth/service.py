"""Authentication service: setup, login, sessions, passwords and user admin.

Every method takes the caller's SQLAlchemy session and commits its own unit of
work, so the HTTP layer and the CLI share identical behaviour.
"""

import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional, Sequence, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from leadgen import config
from leadgen.auth import passwords, rate_limit, recovery, tokens
from leadgen.auth.errors import (
    AccountDisabled,
    AccountLocked,
    InvalidCredentials,
    InvalidRecoveryCode,
    NotFound,
    SetupAlreadyCompleted,
    UsernameTaken,
    ValidationFailed,
)
from leadgen.db import repositories as repo
from leadgen.db.base import utcnow
from leadgen.db.models import ROLE_ADMIN, ROLE_USER, ROLES, User
from leadgen.db.models.auth_session import AuthSession

USERNAME_PATTERN = re.compile(r"[A-Za-z0-9._-]{3,32}\Z")
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 32

TEMPORARY_PASSWORD_BYTES = 12

# Refresh ``last_seen_at`` at most once a minute instead of on every request.
SESSION_TOUCH_SECONDS = 60

INVALID_CREDENTIALS_MESSAGE = "Invalid username or password."
INVALID_RECOVERY_MESSAGE = "Invalid username or recovery code."


@dataclass(frozen=True)
class RequestContext:
    """Client details recorded on sessions and audit events."""

    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


@dataclass(frozen=True)
class AuthenticatedSession:
    """A resolved session cookie: the owning user plus the session row."""

    user: User
    session: AuthSession


@dataclass(frozen=True)
class SessionGrant:
    """A freshly issued session cookie."""

    user: User
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class SetupResult:
    user: User
    token: str
    expires_at: datetime
    recovery_code: str


@dataclass(frozen=True)
class CreatedUser:
    user: User
    temporary_password: str
    recovery_code: str


def normalize_username(username: str) -> str:
    """NFKC + casefold, so usernames compare case-insensitively and safely."""
    return unicodedata.normalize("NFKC", username or "").strip().casefold()


def validate_username(username: str) -> str:
    """Return the trimmed username, or raise ``ValidationFailed``."""
    candidate = (username or "").strip()
    if not USERNAME_PATTERN.fullmatch(candidate):
        raise ValidationFailed(
            f"Usernames must be {USERNAME_MIN_LENGTH}-{USERNAME_MAX_LENGTH} characters and use only "
            "letters, digits, dot, underscore or hyphen."
        )
    return candidate


def generate_temporary_password() -> str:
    """A random password that satisfies the policy without being memorable."""
    return secrets.token_urlsafe(TEMPORARY_PASSWORD_BYTES)


class AuthService:
    """All authentication use-cases, bound to one database session."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── bootstrap ──────────────────────────────────────────────────────────────

    def needs_setup(self) -> bool:
        """True while no account exists — the first visitor becomes the admin."""
        return repo.users.count_users(self.db) == 0

    def setup(self, username: str, password: str, ctx: RequestContext) -> SetupResult:
        """Create the first account as an admin and log it in."""
        rate_limit.check_setup_attempt(ctx.ip_address)
        if not self.needs_setup():
            raise SetupAlreadyCompleted("Setup has already been completed.")

        name = validate_username(username)
        passwords.validate_password(password, username=name)
        code = recovery.generate_recovery_code()

        try:
            user = repo.users.create(
                self.db,
                username=name,
                username_normalized=normalize_username(name),
                password_hash=passwords.hash_password(password),
                recovery_code_hash=self._hash_recovery_code(code),
                role=ROLE_ADMIN,
            )
        except IntegrityError as exc:
            self.db.rollback()
            raise UsernameTaken("That username is already taken.") from exc

        repo.events.record(self.db, event_type="setup_completed", user_id=user.id, **self._context_fields(ctx))
        grant = self._issue_session(user, ctx)
        self.db.commit()
        return SetupResult(user=user, token=grant.token, expires_at=grant.expires_at, recovery_code=code)

    # ── login / logout ─────────────────────────────────────────────────────────

    def login(self, username: str, password: str, ctx: RequestContext) -> SessionGrant:
        """Verify credentials and issue a new session cookie."""
        rate_limit.check_login_attempt(ctx.ip_address)
        normalized = normalize_username(username)
        attempted = (username or "").strip()[:USERNAME_MAX_LENGTH]
        user = repo.users.get_by_normalized_username(self.db, normalized)

        if user is None:
            passwords.dummy_verify()
            repo.events.record(
                self.db,
                event_type="login_failure",
                username_attempted=attempted,
                **self._context_fields(ctx),
            )
            self.db.commit()
            rate_limit.check_login_failure(normalized)
            raise InvalidCredentials(INVALID_CREDENTIALS_MESSAGE)

        now = utcnow()
        if user.locked_until is not None and user.locked_until > now:
            raise AccountLocked(self._lockout_message(user, now))

        if not passwords.verify_password(password, user.password_hash):
            if self._register_failed_login(user, ctx):
                raise AccountLocked(self._lockout_message(user, utcnow()))
            raise InvalidCredentials(INVALID_CREDENTIALS_MESSAGE)

        if not user.is_active:
            raise AccountDisabled("This account has been disabled.")

        if passwords.needs_rehash(user.password_hash):
            user.password_hash = passwords.hash_password(password)
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now

        repo.sessions.purge(self.db)
        grant = self._issue_session(user, ctx)
        repo.events.record(self.db, event_type="login_success", user_id=user.id, **self._context_fields(ctx))
        self.db.commit()
        return grant

    def authenticate(self, token: Optional[str]) -> Optional[AuthenticatedSession]:
        """Resolve a raw cookie token to its user, enforcing expiry and idle timeout."""
        if not token:
            return None

        record = repo.sessions.get_by_token_hash(self.db, tokens.hash_token(token))
        if record is None:
            return None

        now = utcnow()
        if record.revoked_at is not None or record.expires_at <= now:
            return None
        if record.last_seen_at + timedelta(minutes=config.SESSION_IDLE_MINUTES) <= now:
            repo.sessions.revoke(self.db, record, reason="idle_timeout", when=now)
            self.db.commit()
            return None

        user = repo.users.get_by_id(self.db, record.user_id)
        if user is None or not user.is_active:
            return None

        if (now - record.last_seen_at) >= timedelta(seconds=SESSION_TOUCH_SECONDS):
            record.last_seen_at = now
            self.db.commit()
        return AuthenticatedSession(user=user, session=record)

    def logout(self, authenticated: AuthenticatedSession, ctx: RequestContext) -> None:
        """Revoke the current session."""
        repo.sessions.revoke(self.db, authenticated.session, reason="logout")
        repo.events.record(
            self.db, event_type="logout", user_id=authenticated.user.id, **self._context_fields(ctx)
        )
        self.db.commit()

    # ── passwords ──────────────────────────────────────────────────────────────

    def change_password(
        self,
        authenticated: AuthenticatedSession,
        current_password: str,
        new_password: str,
        ctx: RequestContext,
    ) -> Optional[str]:
        """Change the password of the signed-in user.

        Other sessions are revoked. A forced first change also rotates the
        recovery code and returns it, so only the user ever sees it.
        """
        user = authenticated.user
        if not passwords.verify_password(current_password, user.password_hash):
            raise InvalidCredentials("The current password is incorrect.")
        passwords.validate_password(new_password, username=user.username)
        if passwords.verify_password(new_password, user.password_hash):
            raise ValidationFailed("The new password must be different from the current one.")

        was_forced = user.must_change_password
        user.password_hash = passwords.hash_password(new_password)
        user.password_changed_at = utcnow()
        user.must_change_password = False

        issued_code = self._rotate_recovery_code(user) if was_forced else None

        repo.sessions.revoke_all_for_user(
            self.db, user.id, reason="password_changed", except_session_id=authenticated.session.id
        )
        repo.events.record(
            self.db,
            event_type="password_changed",
            user_id=user.id,
            metadata={"forced": was_forced},
            **self._context_fields(ctx),
        )
        self.db.commit()
        return issued_code

    def reset_password(self, username: str, recovery_code: str, new_password: str, ctx: RequestContext) -> str:
        """Reset a forgotten password with the recovery code; returns a fresh code."""
        rate_limit.check_reset_attempt(ctx.ip_address)
        normalized = normalize_username(username)
        attempted = (username or "").strip()[:USERNAME_MAX_LENGTH]
        user = repo.users.get_by_normalized_username(self.db, normalized)

        if user is None:
            passwords.dummy_verify()
            repo.events.record(
                self.db,
                event_type="login_failure",
                username_attempted=attempted,
                metadata={"context": "password_reset"},
                **self._context_fields(ctx),
            )
            self.db.commit()
            raise InvalidRecoveryCode(INVALID_RECOVERY_MESSAGE)

        if not passwords.verify_password(recovery.normalize_recovery_code(recovery_code), user.recovery_code_hash):
            repo.events.record(
                self.db,
                event_type="login_failure",
                user_id=user.id,
                username_attempted=attempted,
                metadata={"context": "password_reset"},
                **self._context_fields(ctx),
            )
            self.db.commit()
            raise InvalidRecoveryCode(INVALID_RECOVERY_MESSAGE)

        if not user.is_active:
            raise AccountDisabled("This account has been disabled.")

        passwords.validate_password(new_password, username=user.username)
        user.password_hash = passwords.hash_password(new_password)
        user.password_changed_at = utcnow()
        user.must_change_password = False
        user.failed_login_attempts = 0
        user.locked_until = None

        issued_code = self._rotate_recovery_code(user)
        repo.sessions.revoke_all_for_user(self.db, user.id, reason="password_reset")
        repo.events.record(self.db, event_type="password_reset", user_id=user.id, **self._context_fields(ctx))
        self.db.commit()
        return issued_code

    def regenerate_recovery_code(self, user: User, password: str, ctx: RequestContext) -> str:
        """Issue a new recovery code after confirming the account password."""
        if not passwords.verify_password(password, user.password_hash):
            raise InvalidCredentials("The password is incorrect.")

        code = self._rotate_recovery_code(user)
        repo.events.record(
            self.db, event_type="recovery_code_regenerated", user_id=user.id, **self._context_fields(ctx)
        )
        self.db.commit()
        return code

    # ── admin ──────────────────────────────────────────────────────────────────

    def list_users(self) -> Sequence[User]:
        return repo.users.list_users(self.db)

    def create_user(
        self,
        *,
        username: str,
        role: str = ROLE_USER,
        created_by: Optional[User] = None,
        ctx: RequestContext,
    ) -> CreatedUser:
        """Create an account with a temporary password the user must replace."""
        name = validate_username(username)
        if role not in ROLES:
            raise ValidationFailed(f"Role must be one of: {', '.join(ROLES)}.")

        temporary_password = generate_temporary_password()
        code = recovery.generate_recovery_code()
        try:
            user = repo.users.create(
                self.db,
                username=name,
                username_normalized=normalize_username(name),
                password_hash=passwords.hash_password(temporary_password),
                recovery_code_hash=self._hash_recovery_code(code),
                role=role,
                must_change_password=True,
                created_by_id=created_by.id if created_by else None,
            )
        except IntegrityError as exc:
            self.db.rollback()
            raise UsernameTaken("That username is already taken.") from exc

        repo.events.record(
            self.db,
            event_type="user_created",
            user_id=user.id,
            metadata={"role": role, "created_by": created_by.username if created_by else None},
            **self._context_fields(ctx),
        )
        self.db.commit()
        return CreatedUser(user=user, temporary_password=temporary_password, recovery_code=code)

    def update_user(
        self,
        *,
        user_id: str,
        is_active: Optional[bool] = None,
        role: Optional[str] = None,
        acting_user: Optional[User] = None,
        ctx: RequestContext,
    ) -> User:
        """Enable/disable an account or change its role."""
        if is_active is None and role is None:
            raise ValidationFailed("Provide at least one field to update.")

        user = repo.users.get_by_id(self.db, user_id)
        if user is None:
            raise NotFound("User not found.")

        if acting_user is not None and user.id == acting_user.id:
            if is_active is False or (role is not None and role != ROLE_ADMIN):
                raise ValidationFailed("You cannot disable or demote your own account.")

        if role is not None:
            if role not in ROLES:
                raise ValidationFailed(f"Role must be one of: {', '.join(ROLES)}.")
            user.role = role

        if is_active is not None and bool(is_active) != user.is_active:
            user.is_active = bool(is_active)
            if user.is_active:
                repo.events.record(
                    self.db, event_type="user_enabled", user_id=user.id, **self._context_fields(ctx)
                )
            else:
                repo.sessions.revoke_all_for_user(self.db, user.id, reason="admin")
                repo.events.record(
                    self.db, event_type="user_disabled", user_id=user.id, **self._context_fields(ctx)
                )

        self.db.commit()
        return user

    def revoke_user_sessions(self, user_id: str) -> int:
        """Force every session of an account to log out."""
        user = repo.users.get_by_id(self.db, user_id)
        if user is None:
            raise NotFound("User not found.")
        count = repo.sessions.revoke_all_for_user(self.db, user.id, reason="admin")
        self.db.commit()
        return count

    def admin_reset_password(self, user: User, ctx: RequestContext) -> Tuple[str, str]:
        """Issue a temporary password plus a new recovery code (CLI recovery path)."""
        temporary_password = generate_temporary_password()
        user.password_hash = passwords.hash_password(temporary_password)
        user.password_changed_at = utcnow()
        user.must_change_password = True
        user.failed_login_attempts = 0
        user.locked_until = None

        code = self._rotate_recovery_code(user)
        repo.sessions.revoke_all_for_user(self.db, user.id, reason="admin")
        repo.events.record(
            self.db,
            event_type="password_reset",
            user_id=user.id,
            metadata={"context": "admin"},
            **self._context_fields(ctx),
        )
        self.db.commit()
        return temporary_password, code

    # ── maintenance ────────────────────────────────────────────────────────────

    def purge_sessions(self) -> int:
        """Delete expired/revoked session rows (called at startup and on login)."""
        count = repo.sessions.purge(self.db)
        self.db.commit()
        return count

    # ── internals ──────────────────────────────────────────────────────────────

    def _issue_session(self, user: User, ctx: RequestContext) -> SessionGrant:
        token = tokens.generate_session_token()
        expires_at = utcnow() + timedelta(hours=config.SESSION_TTL_HOURS)
        repo.sessions.create(
            self.db,
            user_id=user.id,
            token_hash=tokens.hash_token(token),
            expires_at=expires_at,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
        return SessionGrant(user=user, token=token, expires_at=expires_at)

    def _register_failed_login(self, user: User, ctx: RequestContext) -> bool:
        """Count a failed attempt; returns True when this attempt locked the account."""
        now = utcnow()
        if user.locked_until is not None and user.locked_until <= now:
            # The previous lockout expired — start a fresh window.
            user.failed_login_attempts = 0
            user.locked_until = None

        user.failed_login_attempts += 1
        locked_now = user.failed_login_attempts >= config.AUTH_MAX_FAILED_LOGINS
        if locked_now:
            user.locked_until = now + timedelta(minutes=config.AUTH_LOCKOUT_MINUTES)

        repo.events.record(
            self.db,
            event_type="login_failure",
            user_id=user.id,
            username_attempted=user.username,
            metadata={"failed_attempts": user.failed_login_attempts},
            **self._context_fields(ctx),
        )
        if locked_now:
            repo.events.record(
                self.db,
                event_type="account_locked",
                user_id=user.id,
                metadata={"failed_attempts": user.failed_login_attempts, "minutes": config.AUTH_LOCKOUT_MINUTES},
                **self._context_fields(ctx),
            )
        self.db.commit()

        # Rate limiting is checked after the counters are durable, so a 429 does
        # not lose the failed-attempt bookkeeping.
        rate_limit.check_login_failure(user.username_normalized)
        return locked_now

    def _rotate_recovery_code(self, user: User) -> str:
        code = recovery.generate_recovery_code()
        user.recovery_code_hash = self._hash_recovery_code(code)
        user.recovery_code_created_at = utcnow()
        return code

    @staticmethod
    def _hash_recovery_code(code: str) -> str:
        return passwords.hash_password(recovery.normalize_recovery_code(code))

    @staticmethod
    def _lockout_message(user: User, now: datetime) -> str:
        minutes = max(1, int(((user.locked_until or now) - now).total_seconds() // 60) + 1)
        return f"Account locked after too many failed attempts. Try again in {minutes} minute(s)."

    @staticmethod
    def _context_fields(ctx: RequestContext) -> Dict[str, Optional[str]]:
        return {"ip_address": ctx.ip_address, "user_agent": ctx.user_agent}
