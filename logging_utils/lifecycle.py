"""Reliable structured lifecycle instrumentation for concurrent sub-agents."""

import asyncio
from contextlib import contextmanager
from typing import Dict, Iterator

from logging_utils.registry import emit_event


@contextmanager
def subagent_lifecycle(
    *,
    company: str,
    execution_id: str,
    parent_execution_id: str,
    branch: str,
    component: str,
) -> Iterator[Dict[str, object]]:
    """Emit exactly one start and terminal event around a unit of work."""
    base_data = {
        "company": company,
        "execution_id": execution_id,
        "parent_execution_id": parent_execution_id,
        "branch": branch,
    }
    terminal_data: Dict[str, object] = {}
    status = "completed"
    error = None

    emit_event("subagent_start", base_data, component=component)
    try:
        yield terminal_data
    except BaseException as exc:
        status = "cancelled" if isinstance(exc, asyncio.CancelledError) else "error"
        error = str(exc)
        emit_event(
            "subagent_error",
            {
                **base_data,
                "status": status,
                "error": error,
                "error_type": type(exc).__name__,
            },
            component=component,
            level="warning",
        )
        raise
    finally:
        payload = {**base_data, **terminal_data, "status": status}
        if error:
            payload["error"] = error
        emit_event("subagent_end", payload, component=component)
