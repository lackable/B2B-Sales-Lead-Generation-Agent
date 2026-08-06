import sys
from datetime import datetime

def get_timestamp_prefix() -> str:
    """Returns formatted date and time string e.g. [2026-08-01 21:46:35]"""
    return datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")

def log_print(*args, **kwargs):
    """
    Wrapper around print() that prefixes log lines with date and time.
    """
    ts = get_timestamp_prefix()
    if args and isinstance(args[0], str):
        msg = args[0]
        if msg.startswith("\n"):
            first_arg = f"\n{ts} {msg[1:]}"
        else:
            first_arg = f"{ts} {msg}"
        print(first_arg, *args[1:], **kwargs)
    else:
        print(ts, *args, **kwargs)
    
    # Ensure stdout flush for real-time streaming
    if kwargs.get("flush") is None:
        sys.stdout.flush()

    try:
        from logging_utils.registry import emit_event
        message = args[0] if args and isinstance(args[0], str) else ""
        emit_event("log", {"message": str(message)}, component="logging_.logger")
    except Exception:
        pass
