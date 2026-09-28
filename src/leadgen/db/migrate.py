"""Programmatic Alembic runner used by the API lifespan, the CLI and the tests."""

from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from leadgen import config

ALEMBIC_INI = config.ROOT_DIR / "alembic.ini"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _ensure_sqlite_parent_dir(url: str) -> None:
    """SQLite will not create a missing directory, so make it first."""
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database and parsed.database != ":memory:":
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)


def alembic_config(url: Optional[str] = None) -> Config:
    """Built programmatically so it works from any cwd and without ``alembic.ini``.

    ``alembic.ini`` at the repo root is only used by the ``alembic`` CLI.
    """
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", url or config.database_url())
    return cfg


def upgrade_database(url: Optional[str] = None) -> None:
    """Bring the database schema up to ``head``. Safe to call on every startup."""
    target = url or config.database_url()
    _ensure_sqlite_parent_dir(target)
    command.upgrade(alembic_config(target), "head")


def downgrade_database(url: Optional[str] = None) -> None:
    """Roll every migration back (``base``)."""
    command.downgrade(alembic_config(url), "base")
