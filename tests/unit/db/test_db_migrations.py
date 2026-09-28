"""The Alembic migration must apply, match the models, and roll back cleanly."""

import sqlite3

from alembic import command
from sqlalchemy import inspect

from leadgen import config
from leadgen.db import engine as db_engine
from leadgen.db import migrate

EXPECTED_TABLES = ["alembic_version", "auth_events", "auth_sessions", "users"]


def _db_path():
    assert config.APP_DB_URL is not None
    return config.APP_DB_URL.replace("sqlite:///", "")


def _tables() -> list[str]:
    conn = sqlite3.connect(_db_path())
    try:
        return sorted(row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"))
    finally:
        conn.close()


def test_upgrade_creates_every_auth_table(isolated_var):
    migrate.upgrade_database()

    assert _tables() == EXPECTED_TABLES


def test_upgrade_creates_a_missing_parent_directory(isolated_var):
    "(A fresh checkout has no var/data, so the runner has to create it.)"
    assert config.DATA_DIR.exists() is False

    migrate.upgrade_database()

    assert config.DATA_DIR.is_dir()
    assert _tables() == EXPECTED_TABLES


def test_upgrade_is_idempotent(isolated_var):
    migrate.upgrade_database()
    migrate.upgrade_database()

    assert _tables() == EXPECTED_TABLES


def test_downgrade_removes_every_auth_table(isolated_var):
    migrate.upgrade_database()

    migrate.downgrade_database()

    assert _tables() == ["alembic_version"]


def test_migrations_match_the_models(auth_db):
    """`alembic check` raises if the schema drifted from Base.metadata."""
    command.check(migrate.alembic_config())


def test_migrated_schema_exposes_the_expected_indexes(auth_db):
    engine = db_engine.get_engine()
    inspector = inspect(engine)

    assert {index["name"] for index in inspector.get_indexes("auth_sessions")} == {
        "ix_auth_sessions_expires_at",
        "ix_auth_sessions_user_id_revoked_at",
    }
    assert {index["name"] for index in inspector.get_indexes("auth_events")} == {
        "ix_auth_events_event_type_created_at",
        "ix_auth_events_user_id_created_at",
    }
    assert {column["name"] for column in inspector.get_columns("users")} >= {
        "id",
        "username",
        "username_normalized",
        "password_hash",
        "recovery_code_hash",
        "role",
        "is_active",
        "must_change_password",
    }
