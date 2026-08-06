"""
logging_utils — shared structured logging package for Shortlister & LinkedIn Finder agents.

Usage in any agent entrypoint:
    from logging_utils.config import setup_logging
    logger = setup_logging(agent="shortlister", run_id=session_id)
"""

from logging_utils.config import setup_logging
from logging_utils.context import bind_log_context, get_log_context
from logging_utils.registry import emit_event, get_logger, register_logger
from logging_utils.ws_broadcaster import ws_queue

__all__ = [
    "setup_logging",
    "bind_log_context",
    "get_log_context",
    "register_logger",
    "get_logger",
    "emit_event",
    "ws_queue",
]
