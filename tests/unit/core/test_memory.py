"""Unit tests for :mod:`leadgen.core.memory`."""

from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from leadgen import config
from leadgen.core.memory import get_checkpointer


def test_get_checkpointer_uses_config_memory_db_path(isolated_var):
    saver = get_checkpointer()
    try:
        assert isinstance(saver, SqliteSaver)

        db_path = Path(config.MEMORY_DB_PATH)
        assert db_path.exists()
        assert db_path.parent.is_dir()
        # The other agent's database was not touched
        assert not Path(config.LINKEDIN_MEMORY_DB_PATH).exists()
    finally:
        saver.conn.close()


def test_get_checkpointer_creates_parent_directory(isolated_var):
    assert not config.DATA_DIR.exists()
    saver = get_checkpointer()
    try:
        assert config.DATA_DIR.is_dir()
        assert Path(config.MEMORY_DB_PATH).is_file()
    finally:
        saver.conn.close()


def test_get_checkpointer_honours_explicit_path(tmp_path):
    explicit = tmp_path / "custom" / "linkedin.db"

    saver = get_checkpointer(str(explicit))
    try:
        assert isinstance(saver, SqliteSaver)
        assert explicit.is_file()
    finally:
        saver.conn.close()


def test_get_checkpointer_creates_nested_directories(tmp_path):
    nested = tmp_path / "a" / "b" / "c" / "deep.db"

    saver = get_checkpointer(str(nested))
    try:
        assert nested.is_file()
        assert nested.parent.is_dir()
    finally:
        saver.conn.close()
