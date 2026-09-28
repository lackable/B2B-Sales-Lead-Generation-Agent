"""Alembic environment — connects ``Base.metadata`` to the configured database.

The URL comes from ``-x``-free config: ``leadgen.db.migrate`` always injects it,
and the ``alembic`` CLI falls back to ``leadgen.config.database_url()``.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from leadgen import config as app_config
from leadgen.db import models  # noqa: F401  (registers every table on Base.metadata)
from leadgen.db.base import Base

config = context.config

if config.config_file_name is not None and config.get_section("loggers"):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or app_config.database_url()


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection")
    if connectable is None:
        connectable = engine_from_config(
            {"sqlalchemy.url": _database_url()},
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
