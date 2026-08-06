"""Task-local correlation context for structured pipeline logging."""

from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Dict, Iterator


_log_context: ContextVar[Dict[str, Any]] = ContextVar("pipeline_log_context", default={})


def get_log_context() -> Dict[str, Any]:
    """Return a copy of the correlation fields bound to the current task."""
    return dict(_log_context.get())


def push_log_context(**fields: Any) -> Token:
    """Merge fields into the current task context and return a reset token."""
    merged = get_log_context()
    merged.update({key: value for key, value in fields.items() if value is not None})
    return _log_context.set(merged)


def reset_log_context(token: Token) -> None:
    """Restore the task context captured before push_log_context."""
    _log_context.reset(token)


@contextmanager
def bind_log_context(**fields: Any) -> Iterator[None]:
    """Temporarily bind correlation fields for synchronous or async work."""
    token = push_log_context(**fields)
    try:
        yield
    finally:
        reset_log_context(token)
