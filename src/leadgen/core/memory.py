"""SQLite checkpointer factory for LangGraph state persistence."""

import sqlite3
from pathlib import Path
from typing import Optional

from langgraph.checkpoint.sqlite import SqliteSaver

from leadgen import config


def get_checkpointer(db_path: Optional[str] = None) -> SqliteSaver:
    """
    Return a configured SqliteSaver instance.

    Defaults to the Shortlister database (``var/data/shortlister.db``); pass a path
    to keep another agent's checkpoints isolated — the LinkedIn Finder agent uses
    ``config.LINKEDIN_MEMORY_DB_PATH``.
    """
    path = Path(db_path or config.MEMORY_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    return SqliteSaver(conn)
