"""Session factory, the FastAPI ``get_db`` dependency and a unit-of-work helper."""

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy.orm import Session, sessionmaker

from leadgen.db.engine import get_engine

_session_factory: Optional[sessionmaker] = None
_session_factory_engine = None


def get_session_factory() -> sessionmaker:
    """Session factory bound to the current engine (rebuilt when it changes)."""
    global _session_factory, _session_factory_engine

    engine = get_engine()
    if _session_factory is None or _session_factory_engine is not engine:
        _session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
        _session_factory_engine = engine
    return _session_factory


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Unit of work for scripts, the CLI and tests: commit on success, roll back on error."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
