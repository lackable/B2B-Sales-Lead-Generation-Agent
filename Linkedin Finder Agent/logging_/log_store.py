"""
LogStore for LinkedIn Finder Agent — delegates to shared pipeline logger.
"""

import sys
from typing import Optional

_logger = None


def set_logger(logger) -> None:
    global _logger
    _logger = logger
    try:
        from logging_utils.registry import register_logger
        register_logger(logger)
    except Exception:
        pass


class LogStore:
    def __init__(self, run_id: str):
        import os, config
        self.run_id = "".join(c for c in str(run_id) if c.isalnum() or c in ("-", "_")).strip() or "default"
        log_dir = os.path.abspath(config.LOG_DIR)
        self.log_file = os.path.join(log_dir, f"run_{self.run_id}.jsonl")

    def write_event(self, event_type: str, data: dict) -> None:
        try:
            from logging_utils.registry import emit_event
            emitted = emit_event(event_type, data, component="logging_.log_store")
        except Exception:
            emitted = False
        if emitted:
            return
        if _logger is not None:
            _logger.event(event_type, data, component="logging_.log_store")
        else:
            import json
            from datetime import datetime, timezone
            print(
                json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
                            "run_id": self.run_id, "event_type": event_type, "data": data},
                           default=str),
                file=sys.stderr,
                flush=True,
            )
