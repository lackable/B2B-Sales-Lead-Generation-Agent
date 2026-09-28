"""
Structured telemetry for the agent pipeline.

Single logging stack for both agents and the API — merged from the former
``logging_utils`` package and each agent's local ``logging_`` package.

Entry point::

    from leadgen.core.telemetry import setup_logging, set_logger
    logger = setup_logging(agent="shortlister", run_id=session_id)
    set_logger(logger)
"""

from leadgen.core.telemetry.adapter import StructuredLoggerAdapter, setup_logging
from leadgen.core.telemetry.callbacks import PipelineLogger, log_print
from leadgen.core.telemetry.context import bind_log_context, get_log_context
from leadgen.core.telemetry.lifecycle import subagent_lifecycle
from leadgen.core.telemetry.log_store import LogStore, set_logger
from leadgen.core.telemetry.registry import emit_event, get_logger, register_logger
from leadgen.core.telemetry.snapshots import sanitize_decision_makers
from leadgen.core.telemetry.ws_broadcaster import ws_queue

__all__ = [
    "setup_logging",
    "StructuredLoggerAdapter",
    "PipelineLogger",
    "log_print",
    "LogStore",
    "set_logger",
    "bind_log_context",
    "get_log_context",
    "subagent_lifecycle",
    "sanitize_decision_makers",
    "register_logger",
    "get_logger",
    "emit_event",
    "ws_queue",
]
