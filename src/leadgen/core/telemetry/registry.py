"""Process-wide access to the active structured pipeline logger."""

import logging
import threading


_registry_lock = threading.RLock()
_active_logger = None


def register_logger(logger) -> None:
    """Register the logger used by all in-process agent modules."""
    global _active_logger
    with _registry_lock:
        _active_logger = logger


def get_logger():
    """Return the active structured logger, if logging has been configured."""
    with _registry_lock:
        return _active_logger


def emit_event(
    event_type: str,
    data: dict,
    *,
    component: str = "unknown",
    level: str | int = "info",
) -> bool:
    """Emit without depending on either agent's local logging package."""
    logger = get_logger()
    if logger is None:
        return False
    resolved_level = level if isinstance(level, int) else getattr(
        logging, str(level).upper(), logging.INFO
    )
    try:
        logger.event(event_type, data, level=resolved_level, component=component)
        return True
    except Exception:
        return False
