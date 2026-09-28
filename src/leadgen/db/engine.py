"""Engine factory and the per-process engine cache.

The resolved URL comes from ``leadgen.config.database_url()`` (``APP_DB_URL`` or
``<VAR_DIR>/data/app.db``). The cache is keyed by URL, so pointing ``config`` at
a different database — which the test suite does — transparently rebuilds it.
"""

from typing import Optional

from sqlalchemy import Engine, event, create_engine

from leadgen import config

_engine: Optional[Engine] = None
_engine_url: Optional[str] = None


def _apply_sqlite_pragmas(engine: Engine) -> None:
    """Per-connection PRAGMAs: enforce FKs, use WAL, and wait instead of failing."""

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record):  # pragma: no cover - driver callback
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()


def create_db_engine(url: str) -> Engine:
    """Build a new engine for ``url``, tuned for SQLite when applicable."""
    if url.startswith("sqlite"):
        # check_same_thread=False: the API hands sessions to worker threads.
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})
        _apply_sqlite_pragmas(engine)
        return engine
    return create_engine(url)


def get_engine() -> Engine:
    """Return the cached engine, rebuilding it when the configured URL changed."""
    global _engine, _engine_url

    url = config.database_url()
    if _engine is None or _engine_url != url:
        dispose_engine()
        _engine = create_db_engine(url)
        _engine_url = url
    return _engine


def dispose_engine() -> None:
    """Drop the cached engine and close its pooled connections."""
    global _engine, _engine_url

    if _engine is not None:
        _engine.dispose()
    _engine = None
    _engine_url = None
