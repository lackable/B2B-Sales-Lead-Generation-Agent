"""Database-level guarantees: uniqueness, CHECK constraints and FK actions."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from leadgen.db import repositories as repo
from leadgen.db.base import utcnow
from leadgen.db.models import AuthEvent, AuthSession, User


def _user(username="alice", **overrides) -> User:
    now = utcnow()
    values = {
        "username": username,
        "username_normalized": username.casefold(),
        "password_hash": "argon2-hash",
        "recovery_code_hash": "argon2-hash",
        "recovery_code_created_at": now,
        "password_changed_at": now,
    }
    values.update(overrides)
    return User(**values)


def test_username_normalized_is_case_insensitively_unique(db_session):
    db_session.add(_user("Alice"))
    db_session.commit()

    db_session.add(_user("alice", username_normalized="alice"))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    assert repo.users.count_users(db_session) == 1


def test_role_check_constraint_rejects_unknown_roles(db_session):
    db_session.add(_user(role="superuser"))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_event_type_check_constraint_rejects_unknown_events(db_session):
    db_session.add(AuthEvent(event_type="not_a_real_event"))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_session_token_hash_is_unique(db_session):
    user = repo.users.create(
        db_session,
        username="alice",
        username_normalized="alice",
        password_hash="h",
        recovery_code_hash="r",
    )
    db_session.commit()
    expires = utcnow()

    repo.sessions.create(db_session, user_id=user.id, token_hash="same", expires_at=expires)
    db_session.commit()

    # The repository flushes, so the constraint fires before any commit.
    with pytest.raises(IntegrityError):
        repo.sessions.create(db_session, user_id=user.id, token_hash="same", expires_at=expires)
    db_session.rollback()


def test_deleting_a_user_cascades_to_their_sessions(db_session):
    user = repo.users.create(
        db_session,
        username="alice",
        username_normalized="alice",
        password_hash="h",
        recovery_code_hash="r",
    )
    repo.sessions.create(db_session, user_id=user.id, token_hash="token", expires_at=utcnow())
    db_session.commit()
    assert db_session.scalars(select(AuthSession)).all() != []

    db_session.delete(user)
    db_session.commit()

    assert db_session.scalars(select(AuthSession)).all() == []


def test_deleting_a_user_nullifies_their_audit_events(db_session):
    user = repo.users.create(
        db_session,
        username="alice",
        username_normalized="alice",
        password_hash="h",
        recovery_code_hash="r",
    )
    repo.events.record(db_session, event_type="login_success", user_id=user.id)
    db_session.commit()

    db_session.delete(user)
    db_session.commit()
    db_session.expire_all()

    event = db_session.scalars(select(AuthEvent)).one()
    assert event.user_id is None
    assert event.event_type == "login_success"


def test_self_referencing_creator_fk_survives_a_deleted_creator(db_session):
    admin = repo.users.create(
        db_session,
        username="admin",
        username_normalized="admin",
        password_hash="h",
        recovery_code_hash="r",
        role="admin",
    )
    member = repo.users.create(
        db_session,
        username="bob",
        username_normalized="bob",
        password_hash="h",
        recovery_code_hash="r",
        created_by_id=admin.id,
    )
    db_session.commit()

    db_session.delete(admin)
    db_session.commit()
    db_session.expire_all()

    assert db_session.get(User, member.id).created_by_id is None
