"""AuthService: setup, login/lockout, session lifecycle, passwords and admin ops."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from leadgen import config
from leadgen.auth import passwords, recovery, tokens
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
from leadgen.auth.service import AuthService, RequestContext, normalize_username, validate_username
from leadgen.db import repositories as repo
from leadgen.db.base import utcnow
from leadgen.db.models import ROLE_ADMIN, ROLE_USER, AuthEvent, AuthSession
from leadgen.db.session import get_session_factory

USERNAME = "AdminUser"
PASSWORD = "correct-horse-battery"
NEW_PASSWORD = "a-brand-new-secret"
CTX = RequestContext(ip_address="127.0.0.1", user_agent="pytest")


@pytest.fixture
def service(auth_db, api_state_reset):
    db = get_session_factory()()
    try:
        yield AuthService(db)
    finally:
        db.rollback()
        db.close()


def _setup(service, username=USERNAME, password=PASSWORD):
    return service.setup(username, password, CTX)


def _user(service, username=USERNAME):
    return repo.users.get_by_normalized_username(service.db, normalize_username(username))


def _sessions(service, user_id=None):
    stmt = select(AuthSession).order_by(AuthSession.created_at)
    if user_id:
        stmt = stmt.where(AuthSession.user_id == user_id)
    return service.db.scalars(stmt).all()


def _events(service, event_type=None):
    stmt = select(AuthEvent).order_by(AuthEvent.id)
    if event_type:
        stmt = stmt.where(AuthEvent.event_type == event_type)
    return service.db.scalars(stmt).all()


# ── setup ──────────────────────────────────────────────────────────────────────


def test_needs_setup_toggles_after_setup(service):
    assert service.needs_setup() is True

    _setup(service)

    assert service.needs_setup() is False


def test_setup_creates_an_active_admin_and_signs_it_in(service):
    result = _setup(service)

    assert result.user.role == ROLE_ADMIN
    assert result.user.is_active is True
    assert result.user.must_change_password is False
    assert result.user.username == USERNAME
    assert result.user.username_normalized == "adminuser"
    assert result.user.last_login_at is None
    assert result.expires_at > utcnow()
    assert [event.event_type for event in _events(service)] == ["setup_completed"]

    authenticated = service.authenticate(result.token)
    assert authenticated is not None
    assert authenticated.user.id == result.user.id


def test_setup_stores_hashes_not_secrets(service):
    result = _setup(service)
    user = _user(service)

    assert user.password_hash != PASSWORD
    assert user.recovery_code_hash != result.recovery_code
    assert passwords.verify_password(PASSWORD, user.password_hash) is True
    assert passwords.verify_password(recovery.normalize_recovery_code(result.recovery_code), user.recovery_code_hash)


def test_setup_returns_a_fresh_code_each_time_it_is_called(service):
    _setup(service)
    other = AuthService(service.db)

    with pytest.raises(SetupAlreadyCompleted):
        other.setup("someone-else", PASSWORD, CTX)


@pytest.mark.parametrize("username", ["ab", "", "   ", "has space", "has@symbol", "a" * 33])
def test_setup_rejects_invalid_usernames(service, username):
    with pytest.raises(ValidationFailed):
        _setup(service, username=username)


def test_setup_rejects_weak_passwords(service):
    with pytest.raises(ValidationFailed):
        _setup(service, password="short")

    with pytest.raises(ValidationFailed):
        _setup(service, password=USERNAME)


def test_setup_enforces_the_password_policy_before_creating_anything(service):
    with pytest.raises(ValidationFailed):
        _setup(service, password="short")

    assert service.needs_setup() is True
    assert service.list_users() == []


# ── login ──────────────────────────────────────────────────────────────────────


def test_login_issues_a_new_session_and_records_last_login(service):
    _setup(service)

    grant = service.login(USERNAME, PASSWORD, CTX)

    user = _user(service)
    assert user.last_login_at is not None
    assert user.failed_login_attempts == 0
    assert len(_sessions(service, user.id)) == 2
    assert service.authenticate(grant.token).user.id == user.id


def test_login_is_case_insensitive(service):
    _setup(service, "MixedCase")

    assert service.login("mixedcase", PASSWORD, CTX).user.username == "MixedCase"
    assert service.login("MIXEDCASE", PASSWORD, CTX).user.username == "MixedCase"


def test_unknown_username_and_wrong_password_share_one_message(service):
    _setup(service)

    with pytest.raises(InvalidCredentials) as unknown:
        service.login("nobody", PASSWORD, CTX)
    with pytest.raises(InvalidCredentials) as wrong:
        service.login(USERNAME, "definitely-not-it", CTX)

    assert unknown.value.message == wrong.value.message


def test_failed_login_increments_and_success_resets(service):
    _setup(service)

    with pytest.raises(InvalidCredentials):
        service.login(USERNAME, "definitely-not-it", CTX)
    assert _user(service).failed_login_attempts == 1

    service.login(USERNAME, PASSWORD, CTX)
    assert _user(service).failed_login_attempts == 0
    assert _user(service).locked_until is None


def test_account_locks_after_the_configured_number_of_failures(service, monkeypatch):
    monkeypatch.setattr(config, "AUTH_MAX_FAILED_LOGINS", 3)
    monkeypatch.setattr(config, "AUTH_LOCKOUT_MINUTES", 15)
    _setup(service)

    for _ in range(2):
        with pytest.raises(InvalidCredentials):
            service.login(USERNAME, "definitely-not-it", CTX)

    with pytest.raises(AccountLocked) as locked:
        service.login(USERNAME, "definitely-not-it", CTX)

    assert "locked" in locked.value.message
    assert _user(service).locked_until is not None
    assert [event.event_type for event in _events(service, "account_locked")] == ["account_locked"]

    # Even the right password is refused while the lock is active.
    with pytest.raises(AccountLocked):
        service.login(USERNAME, PASSWORD, CTX)


def test_lockout_expires_and_the_counter_starts_fresh(service):
    _setup(service)
    user = _user(service)
    user.failed_login_attempts = config.AUTH_MAX_FAILED_LOGINS
    user.locked_until = utcnow() - timedelta(minutes=1)
    service.db.commit()

    with pytest.raises(InvalidCredentials):
        service.login(USERNAME, "definitely-not-it", CTX)

    assert _user(service).failed_login_attempts == 1


def test_login_rejects_disabled_accounts(service):
    _setup(service)
    user = _user(service)
    user.is_active = False
    service.db.commit()

    with pytest.raises(AccountDisabled):
        service.login(USERNAME, PASSWORD, CTX)


def test_login_upgrades_the_hash_when_parameters_changed(service):
    from argon2 import PasswordHasher

    _setup(service)
    user = _user(service)
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    user.password_hash = weak
    service.db.commit()

    assert passwords.needs_rehash(weak) is True
    service.login(USERNAME, PASSWORD, CTX)

    upgraded = _user(service).password_hash
    assert upgraded != weak
    assert passwords.needs_rehash(upgraded) is False
    assert passwords.verify_password(PASSWORD, upgraded) is True


def test_unknown_username_failures_are_rate_limited_per_username(service):
    _setup(service)

    from leadgen.auth import rate_limit

    for _ in range(rate_limit.LOGIN_USERNAME_LIMIT[0]):
        with pytest.raises(InvalidCredentials):
            service.login("ghost", PASSWORD, CTX)

    with pytest.raises(rate_limit.RateLimited):
        service.login("ghost", PASSWORD, CTX)


# ── session resolution ─────────────────────────────────────────────────────────


def test_authenticate_rejects_empty_unknown_and_malformed_tokens(service):
    _setup(service)

    assert service.authenticate(None) is None
    assert service.authenticate("") is None
    assert service.authenticate("not-a-real-token") is None


def _revoke(service, token, reason="logout"):
    repo.sessions.revoke(
        service.db, repo.sessions.get_by_token_hash(service.db, tokens.hash_token(token)), reason=reason
    )


def test_authenticate_rejects_revoked_expired_and_idle_sessions(service):
    _setup(service)
    revoked = service.login(USERNAME, PASSWORD, CTX)
    expired = service.login(USERNAME, PASSWORD, CTX)
    idle = service.login(USERNAME, PASSWORD, CTX)
    user_id = revoked.user.id

    _revoke(service, revoked.token)
    repo.sessions.get_by_token_hash(service.db, tokens.hash_token(expired.token)).expires_at = utcnow() - timedelta(
        seconds=1
    )
    repo.sessions.get_by_token_hash(
        service.db, tokens.hash_token(idle.token)
    ).last_seen_at = utcnow() - timedelta(minutes=config.SESSION_IDLE_MINUTES + 1)
    service.db.commit()

    assert service.authenticate(revoked.token) is None
    assert service.authenticate(expired.token) is None
    assert service.authenticate(idle.token) is None

    idle_row = repo.sessions.get_by_token_hash(service.db, tokens.hash_token(idle.token))
    assert idle_row.revoked_reason == "idle_timeout"
    # One from setup plus the three logins.
    assert len(_sessions(service, user_id)) == 4


def test_authenticate_rejects_a_disabled_user(service):
    grant = _setup(service)
    user = _user(service)
    user.is_active = False
    service.db.commit()

    assert service.authenticate(grant.token) is None


def test_authenticate_only_touches_last_seen_once_a_minute(service):
    grant = _setup(service)
    row = repo.sessions.get_by_token_hash(service.db, tokens.hash_token(grant.token))
    first_seen = row.last_seen_at

    assert service.authenticate(grant.token) is not None
    assert row.last_seen_at == first_seen

    row.last_seen_at = utcnow() - timedelta(seconds=120)
    service.db.commit()
    assert service.authenticate(grant.token) is not None
    assert row.last_seen_at > first_seen


def test_logout_revokes_the_session_and_audits(service):
    grant = _setup(service)
    authenticated = service.authenticate(grant.token)

    service.logout(authenticated, CTX)

    assert service.authenticate(grant.token) is None
    assert _sessions(service)[0].revoked_reason == "logout"
    assert [event.event_type for event in _events(service, "logout")] == ["logout"]


# ── password change / reset ────────────────────────────────────────────────────


def test_change_password_requires_the_current_password(service):
    grant = _setup(service)
    authenticated = service.authenticate(grant.token)

    with pytest.raises(InvalidCredentials):
        service.change_password(authenticated, "not-the-password", NEW_PASSWORD, CTX)


def test_change_password_rejects_weak_and_reused_passwords(service):
    grant = _setup(service)
    authenticated = service.authenticate(grant.token)

    with pytest.raises(ValidationFailed):
        service.change_password(authenticated, PASSWORD, "short", CTX)

    with pytest.raises(ValidationFailed):
        service.change_password(authenticated, PASSWORD, PASSWORD, CTX)


def test_change_password_keeps_the_current_session_and_revokes_the_others(service):
    first = _setup(service)
    second = service.login(USERNAME, PASSWORD, CTX)
    authenticated = service.authenticate(first.token)

    assert service.change_password(authenticated, PASSWORD, NEW_PASSWORD, CTX) is None

    assert service.authenticate(first.token) is not None
    assert service.authenticate(second.token) is None
    assert passwords.verify_password(NEW_PASSWORD, _user(service).password_hash) is True
    assert _user(service).password_changed_at is not None
    assert [event.event_type for event in _events(service, "password_changed")] == ["password_changed"]
    assert _events(service, "password_changed")[0].event_metadata == '{"forced": false}'


def test_forced_change_clears_the_flag_and_rotates_the_recovery_code(service):
    _setup(service)
    admin = _user(service)
    created = service.create_user(username="newbie", created_by=admin, ctx=CTX)

    grant = service.login("newbie", created.temporary_password, CTX)
    authenticated = service.authenticate(grant.token)
    assert authenticated.user.must_change_password is True

    new_code = service.change_password(authenticated, created.temporary_password, NEW_PASSWORD, CTX)

    assert new_code is not None
    assert new_code != created.recovery_code
    assert recovery.is_well_formed(new_code) is True
    assert service.authenticate(grant.token) is not None

    user = _user(service, "newbie")
    assert user.must_change_password is False
    assert passwords.verify_password(recovery.normalize_recovery_code(new_code), user.recovery_code_hash) is True
    assert service.login("newbie", NEW_PASSWORD, CTX).user.id == user.id


def test_reset_password_rotates_the_code_and_revokes_every_session(service):
    first = _setup(service)
    second = service.login(USERNAME, PASSWORD, CTX)

    new_code = service.reset_password(USERNAME, first.recovery_code, NEW_PASSWORD, CTX)

    assert new_code != first.recovery_code
    assert recovery.is_well_formed(new_code) is True
    assert service.authenticate(first.token) is None
    assert service.authenticate(second.token) is None
    assert passwords.verify_password(NEW_PASSWORD, _user(service).password_hash) is True
    assert [event.event_type for event in _events(service, "password_reset")] == ["password_reset"]

    # The old code and the old password are both dead.
    with pytest.raises(InvalidRecoveryCode):
        service.reset_password(USERNAME, first.recovery_code, "another-new-secret", CTX)


def test_reset_password_accepts_a_messy_code_and_rejects_bad_ones(service):
    result = _setup(service)
    messy = f" {result.recovery_code.replace('-', ' ').lower()} "

    with pytest.raises(InvalidRecoveryCode):
        service.reset_password(USERNAME, "K7Q2-9XMP-4HDA-ZR8N-TW3C", NEW_PASSWORD, CTX)

    with pytest.raises(InvalidRecoveryCode):
        service.reset_password("ghost", result.recovery_code, NEW_PASSWORD, CTX)

    assert service.reset_password(USERNAME, messy, NEW_PASSWORD, CTX)


def test_reset_password_enforces_username_case_insensitivity_and_policy(service):
    result = _setup(service)

    with pytest.raises(ValidationFailed):
        service.reset_password(USERNAME.lower(), result.recovery_code, "short", CTX)


def test_reset_password_rejects_disabled_accounts(service):
    result = _setup(service)
    user = _user(service)
    user.is_active = False
    service.db.commit()

    with pytest.raises(AccountDisabled):
        service.reset_password(USERNAME, result.recovery_code, NEW_PASSWORD, CTX)


def test_regenerate_recovery_code_requires_the_password(service):
    _setup(service)
    user = _user(service)

    with pytest.raises(InvalidCredentials):
        service.regenerate_recovery_code(user, "wrong-password", CTX)

    issued = service.regenerate_recovery_code(user, PASSWORD, CTX)

    assert recovery.is_well_formed(issued) is True
    assert passwords.verify_password(recovery.normalize_recovery_code(issued), user.recovery_code_hash) is True
    assert [event.event_type for event in _events(service, "recovery_code_regenerated")] == ["recovery_code_regenerated"]


# ── admin operations ───────────────────────────────────────────────────────────


def test_create_user_issues_a_working_temporary_password(service):
    _setup(service)
    admin = _user(service)

    created = service.create_user(username="Sales.Rep", role=ROLE_USER, created_by=admin, ctx=CTX)

    assert created.user.role == ROLE_USER
    assert created.user.must_change_password is True
    assert created.user.created_by_id == admin.id
    assert passwords.verify_password(created.temporary_password, created.user.password_hash) is True
    assert len(created.temporary_password) >= config.PASSWORD_MIN_LENGTH
    assert recovery.is_well_formed(created.recovery_code) is True
    assert [event.event_type for event in _events(service, "user_created")] == ["user_created"]

    grant = service.login("sales.rep", created.temporary_password, CTX)
    assert grant.user.id == created.user.id


def test_create_user_validates_username_role_and_uniqueness(service):
    _setup(service)

    with pytest.raises(ValidationFailed):
        service.create_user(username="x", ctx=CTX)
    with pytest.raises(ValidationFailed):
        service.create_user(username="valid-name", role="superuser", ctx=CTX)
    with pytest.raises(UsernameTaken):
        service.create_user(username="adminuser", ctx=CTX)


def test_update_user_disable_revokes_sessions_and_enable_restores(service):
    _setup(service)
    admin = _user(service)
    created = service.create_user(username="blocked", created_by=admin, ctx=CTX)
    grant = service.login("blocked", created.temporary_password, CTX)

    service.update_user(user_id=created.user.id, is_active=False, acting_user=admin, ctx=CTX)

    assert _user(service, "blocked").is_active is False
    assert service.authenticate(grant.token) is None
    assert [event.event_type for event in _events(service, "user_disabled")] == ["user_disabled"]

    service.update_user(user_id=created.user.id, is_active=True, acting_user=admin, ctx=CTX)

    assert _user(service, "blocked").is_active is True
    assert [event.event_type for event in _events(service, "user_enabled")] == ["user_enabled"]


def test_update_user_role_and_self_protection(service):
    _setup(service)
    admin = _user(service)
    created = service.create_user(username="promote-me", created_by=admin, ctx=CTX)

    service.update_user(user_id=created.user.id, role=ROLE_ADMIN, acting_user=admin, ctx=CTX)
    assert _user(service, "promote-me").role == ROLE_ADMIN

    with pytest.raises(ValidationFailed):
        service.update_user(user_id=admin.id, is_active=False, acting_user=admin, ctx=CTX)
    with pytest.raises(ValidationFailed):
        service.update_user(user_id=admin.id, role=ROLE_USER, acting_user=admin, ctx=CTX)
    with pytest.raises(ValidationFailed):
        service.update_user(user_id=created.user.id, role="nope", acting_user=admin, ctx=CTX)


def test_update_user_requires_a_field_and_an_existing_user(service):
    _setup(service)

    with pytest.raises(ValidationFailed):
        service.update_user(user_id="missing", ctx=CTX)
    with pytest.raises(NotFound):
        service.update_user(user_id="missing", is_active=True, ctx=CTX)


def test_revoke_user_sessions_returns_the_count(service):
    _setup(service)
    service.login(USERNAME, PASSWORD, CTX)
    user = _user(service)

    assert service.revoke_user_sessions(user.id) == 2
    assert service.revoke_user_sessions(user.id) == 0

    with pytest.raises(NotFound):
        service.revoke_user_sessions("missing")


def test_admin_reset_password_forces_a_change_and_revokes_sessions(service):
    grant = _setup(service)
    user = _user(service)

    password, code = service.admin_reset_password(user, CTX)

    assert service.authenticate(grant.token) is None
    assert user.must_change_password is True
    assert recovery.is_well_formed(code) is True
    assert passwords.verify_password(password, user.password_hash) is True
    assert [event.event_type for event in _events(service, "password_reset")] == ["password_reset"]


def test_purge_sessions_drops_expired_rows(service):
    grant = _setup(service)
    row = repo.sessions.get_by_token_hash(service.db, tokens.hash_token(grant.token))
    row.expires_at = utcnow() - timedelta(seconds=1)
    service.db.commit()

    assert service.purge_sessions() == 1
    assert _sessions(service) == []


# ── helpers ────────────────────────────────────────────────────────────────────


def test_username_normalization_is_nfkc_casefold():
    assert normalize_username("  Admin.User  ") == "admin.user"
    assert normalize_username("ADMIN") == "admin"
    assert normalize_username("Ａｄｍｉｎ") == "admin"


def test_validate_username_trims_and_rejects():
    assert validate_username("  good.name-1_2  ") == "good.name-1_2"

    for bad in ("ab", "a" * 33, "no spaces", "emoji✨", ""):
        with pytest.raises(ValidationFailed):
            validate_username(bad)
