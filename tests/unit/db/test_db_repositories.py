"""Repository behaviour: user lookup, session lifecycle and the audit log."""

from datetime import timedelta

from sqlalchemy import select

from leadgen.db import repositories as repo
from leadgen.db.base import utcnow
from leadgen.db.models import AuthEvent, AuthSession


def _make_user(db, username="alice", **kwargs):
    user = repo.users.create(
        db,
        username=username,
        username_normalized=username.casefold(),
        password_hash=f"hash-{username}",
        recovery_code_hash=f"recovery-{username}",
        **kwargs,
    )
    db.commit()
    return user


def test_create_assigns_an_id_and_defaults(db_session):
    user = _make_user(db_session)

    assert user.id and len(user.id) == 36
    assert user.role == "user"
    assert user.is_active is True
    assert user.must_change_password is False
    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    assert user.last_login_at is None
    assert user.created_at == user.updated_at


def test_lookup_helpers(db_session):
    alice = _make_user(db_session, "Alice")
    _make_user(db_session, "bob", role="admin")

    assert repo.users.count_users(db_session) == 2
    assert repo.users.get_by_id(db_session, alice.id) is alice
    assert repo.users.get_by_id(db_session, "missing") is None
    assert repo.users.get_by_normalized_username(db_session, "alice") is alice
    assert repo.users.get_by_normalized_username(db_session, "ALICE") is None
    assert [user.username for user in repo.users.list_users(db_session)] == ["Alice", "bob"]


def test_created_by_is_recorded(db_session):
    admin = _make_user(db_session, "admin", role="admin")

    member = _make_user(db_session, "bob", created_by_id=admin.id)

    assert member.created_by_id == admin.id


def test_session_lifecycle(db_session):
    user = _make_user(db_session)
    expires = utcnow() + timedelta(hours=1)

    created = repo.sessions.create(
        db_session,
        user_id=user.id,
        token_hash="abc123",
        expires_at=expires,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )
    db_session.commit()

    assert created.id and created.revoked_at is None
    assert created.created_at == created.last_seen_at
    assert repo.sessions.get_by_token_hash(db_session, "abc123") is created
    assert repo.sessions.get_by_token_hash(db_session, "nope") is None
    assert created.ip_address == "127.0.0.1"

    repo.sessions.revoke(db_session, created, reason="logout")
    db_session.commit()

    assert created.revoked_at is not None
    assert created.revoked_reason == "logout"

    # Revoking twice must not move the original timestamp or reason.
    first_revoked_at = created.revoked_at
    repo.sessions.revoke(db_session, created, reason="password_reset")
    assert created.revoked_at == first_revoked_at
    assert created.revoked_reason == "logout"


def test_revoke_all_for_user_can_spare_one_session(db_session):
    user = _make_user(db_session)
    expires = utcnow() + timedelta(hours=1)
    keep = repo.sessions.create(db_session, user_id=user.id, token_hash="keep", expires_at=expires)
    drop_a = repo.sessions.create(db_session, user_id=user.id, token_hash="drop-a", expires_at=expires)
    drop_b = repo.sessions.create(db_session, user_id=user.id, token_hash="drop-b", expires_at=expires)
    db_session.commit()

    revoked = repo.sessions.revoke_all_for_user(
        db_session, user.id, reason="password_changed", except_session_id=keep.id
    )
    db_session.commit()
    # The bulk UPDATE bypasses the identity map, so reload before asserting.
    db_session.expire_all()

    assert revoked == 2
    assert keep.revoked_at is None
    assert drop_a.revoked_reason == "password_changed"
    assert drop_b.revoked_reason == "password_changed"

    # A second sweep only touches whatever is still live.
    assert repo.sessions.revoke_all_for_user(db_session, user.id, reason="admin") == 1


def test_purge_removes_expired_and_old_revoked_sessions_only(db_session):
    user = _make_user(db_session)
    now = utcnow()

    expired = repo.sessions.create(
        db_session, user_id=user.id, token_hash="expired", expires_at=now - timedelta(seconds=1)
    )
    revoked_old = repo.sessions.create(
        db_session, user_id=user.id, token_hash="revoked-old", expires_at=now + timedelta(days=1)
    )
    revoked_recent = repo.sessions.create(
        db_session, user_id=user.id, token_hash="revoked-recent", expires_at=now + timedelta(days=1)
    )
    live = repo.sessions.create(
        db_session, user_id=user.id, token_hash="live", expires_at=now + timedelta(days=1)
    )
    repo.sessions.revoke(db_session, revoked_old, reason="logout", when=now - timedelta(hours=48))
    repo.sessions.revoke(db_session, revoked_recent, reason="logout", when=now - timedelta(hours=1))
    db_session.commit()

    assert repo.sessions.purge(db_session, now=now) == 2
    db_session.commit()

    remaining = {session.token_hash for session in db_session.scalars(select(AuthSession)).all()}
    assert remaining == {"revoked-recent", "live"}
    assert expired.id not in remaining
    assert live.id is not None


def test_event_rows_default_to_naive_utc_and_store_json_metadata(db_session):
    user = _make_user(db_session)

    repo.events.record(
        db_session,
        event_type="login_failure",
        username_attempted="ghost",
        ip_address="10.0.0.1",
        user_agent="curl",
        metadata={"reason": "bad password", "attempt": 3},
    )
    repo.events.record(db_session, event_type="login_success", user_id=user.id)
    db_session.commit()

    failure, success = db_session.scalars(select(AuthEvent).order_by(AuthEvent.id)).all()

    assert failure.user_id is None
    assert failure.username_attempted == "ghost"
    assert failure.event_metadata == '{"reason": "bad password", "attempt": 3}'
    assert failure.created_at.tzinfo is None
    assert success.user_id == user.id
    assert success.event_metadata is None
