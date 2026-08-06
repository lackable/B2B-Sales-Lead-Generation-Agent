import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
import config

def get_checkpointer() -> SqliteSaver:
    """Returns a configured SqliteSaver instance using the path specified in config.py."""
    conn = sqlite3.connect(config.MEMORY_DB_PATH, check_same_thread=False)
    return SqliteSaver(conn)
