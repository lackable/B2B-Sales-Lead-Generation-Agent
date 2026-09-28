"""Unit tests for :mod:`leadgen.config`."""

import importlib
import os
from pathlib import Path

from leadgen import config

# ── Path settings exposed as ``Path`` objects (absolute, gitignored) ──────────
_PATH_SETTINGS = [
    "DATA_DIR",
    "RUNS_DIR",
    "EXPORTS_DIR",
    "LOGS_DIR",
    "SHORTLISTER_OUTPUT_DIR",
    "SHORTLISTER_REPORTS_DIR",
    "LINKEDIN_OUTPUT_DIR",
]

# ── Path settings exposed as absolute strings for the agents ──────────────────
_STRING_PATH_SETTINGS = [
    "MEMORY_DB_PATH",
    "LINKEDIN_MEMORY_DB_PATH",
    "EXCEL_OUTPUT_DIR",
    "REPORTS_OUTPUT_DIR",
    "OUTPUT_DIR",
    "LOG_DIR",
]

# ── The six artifact dirs ``ensure_runtime_dirs`` must create ─────────────────
_RUNTIME_DIRS = [
    "DATA_DIR",
    "EXPORTS_DIR",
    "LOGS_DIR",
    "SHORTLISTER_OUTPUT_DIR",
    "SHORTLISTER_REPORTS_DIR",
    "LINKEDIN_OUTPUT_DIR",
]

# Env vars whose alias resolution the reload test exercises
_ENV_KEYS = [
    "HUNTER_API_KEY",
    "HUNTER_KEY",
    "API_KEY",
    "BRIGHT_DATA_API_KEY",
    "BRIGHTDATA_TOKEN",
    "OPENAI_MODELS",
    "OPENAI_MODEL",
]


def test_root_dir_is_repo_root_containing_pyproject():
    assert (config.ROOT_DIR / "pyproject.toml").is_file()
    assert (config.ROOT_DIR / "src" / "leadgen").is_dir()
    assert config.ROOT_DIR.is_absolute()


def test_var_dir_defaults_under_root_dir():
    assert config.VAR_DIR == config.ROOT_DIR / "var"
    assert config.VAR_DIR.is_absolute()


def test_every_path_setting_is_absolute():
    for name in _PATH_SETTINGS:
        value = getattr(config, name)
        assert isinstance(value, Path), name
        assert value.is_absolute(), name

    for name in _STRING_PATH_SETTINGS:
        value = getattr(config, name)
        assert isinstance(value, str), name
        assert Path(value).is_absolute(), name


def test_memory_db_paths_are_per_agent_db_files_under_data_dir():
    shortlister = Path(config.MEMORY_DB_PATH)
    linkedin = Path(config.LINKEDIN_MEMORY_DB_PATH)

    assert shortlister.parent == config.DATA_DIR
    assert linkedin.parent == config.DATA_DIR

    assert shortlister.name == "shortlister.db"
    assert linkedin.name == "linkedin.db"
    assert shortlister.suffix == ".db"
    assert linkedin.suffix == ".db"
    assert shortlister != linkedin


def test_runs_subdirs_are_grouped_under_runs_dir():
    assert config.SHORTLISTER_OUTPUT_DIR == config.RUNS_DIR / "shortlister"
    assert config.SHORTLISTER_REPORTS_DIR == config.SHORTLISTER_OUTPUT_DIR / "reports"
    assert config.LINKEDIN_OUTPUT_DIR == config.RUNS_DIR / "linkedin"
    assert config.EXCEL_OUTPUT_DIR == str(config.SHORTLISTER_OUTPUT_DIR)
    assert config.REPORTS_OUTPUT_DIR == str(config.SHORTLISTER_REPORTS_DIR)
    assert config.OUTPUT_DIR == str(config.LINKEDIN_OUTPUT_DIR)


def test_ensure_runtime_dirs_creates_all_six_dirs(isolated_var):
    for name in _RUNTIME_DIRS:
        assert not getattr(config, name).exists(), name

    config.ensure_runtime_dirs()

    for name in _RUNTIME_DIRS:
        assert getattr(config, name).is_dir(), name


def test_ensure_runtime_dirs_is_idempotent_and_preserves_contents(isolated_var):
    config.ensure_runtime_dirs()
    marker = config.DATA_DIR / "keep.txt"
    marker.write_text("x", encoding="utf-8")

    config.ensure_runtime_dirs()  # second call must not raise or wipe anything

    assert marker.read_text(encoding="utf-8") == "x"
    for name in _RUNTIME_DIRS:
        assert getattr(config, name).is_dir(), name


def test_api_key_attributes_are_str_or_none():
    for name in ("HUNTER_API_KEY", "BRIGHT_DATA_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_KEY"):
        value = getattr(config, name)
        assert value is None or isinstance(value, str), name


def test_openai_models_is_a_list_of_strings():
    assert isinstance(config.OPENAI_MODELS, list)
    assert all(isinstance(model, str) for model in config.OPENAI_MODELS)


def test_rate_limit_wait_default_is_int():
    assert isinstance(config.RATE_LIMIT_CYCLE_WAIT_SECONDS, int)
    assert config.RATE_LIMIT_CYCLE_WAIT_SECONDS > 0


def test_env_alias_precedence_and_model_list_parsing():
    """Reload the module under controlled env vars to exercise precedence."""
    saved = {key: os.environ.get(key) for key in _ENV_KEYS}

    def set_env(**values):
        for key, val in values.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

    try:
        # Hunter: primary env var wins over both aliases
        set_env(HUNTER_API_KEY="primary", HUNTER_KEY="from_hunter_key", API_KEY="from_api_key")
        importlib.reload(config)
        assert config.HUNTER_API_KEY == "primary"

        # Hunter: empty primary falls back to HUNTER_KEY
        set_env(HUNTER_API_KEY="")
        importlib.reload(config)
        assert config.HUNTER_API_KEY == "from_hunter_key"

        # Hunter: both empty -> API_KEY alias
        set_env(HUNTER_KEY="")
        importlib.reload(config)
        assert config.HUNTER_API_KEY == "from_api_key"

        # Bright Data: primary wins
        set_env(BRIGHT_DATA_API_KEY="bd_primary", BRIGHTDATA_TOKEN="bd_alias")
        importlib.reload(config)
        assert config.BRIGHT_DATA_API_KEY == "bd_primary"

        # Bright Data: empty primary falls back to BRIGHTDATA_TOKEN alias
        set_env(BRIGHT_DATA_API_KEY="")
        importlib.reload(config)
        assert config.BRIGHT_DATA_API_KEY == "bd_alias"

        # OPENAI_MODELS: comma-separated, blanks stripped
        set_env(OPENAI_MODELS="gpt-a, gpt-b ,, gpt-c")
        importlib.reload(config)
        assert config.OPENAI_MODELS == ["gpt-a", "gpt-b", "gpt-c"]

        # OPENAI_MODELS unset -> single OPENAI_MODEL wrapped in a list
        set_env(OPENAI_MODELS=None, OPENAI_MODEL="gpt-solo")
        importlib.reload(config)
        assert config.OPENAI_MODELS == ["gpt-solo"]

        # Neither set -> empty list
        set_env(OPENAI_MODEL=None)
        importlib.reload(config)
        assert config.OPENAI_MODELS == []
    finally:
        set_env(**saved)
        importlib.reload(config)
