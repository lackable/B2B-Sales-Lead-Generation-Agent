"""Unit tests for the LinkedIn Finder agent ``Configuration`` model."""

from leadgen import config
from leadgen.agents.linkedin_finder.configuration import Configuration

EXPECTED_DEFAULTS = {
    "max_structured_output_retries": 3,
    "research_model_max_tokens": 8192,
}


def test_defaults_match_declared_values():
    cfg = Configuration()

    assert cfg.max_structured_output_retries == 3
    assert cfg.research_model_max_tokens == 8192
    assert cfg.research_model == (config.OPENAI_MODEL or "gpt-4o-mini")

    for field_name, expected in EXPECTED_DEFAULTS.items():
        assert Configuration.model_fields[field_name].default == expected


def test_research_model_default_follows_config_openai_model():
    assert Configuration.model_fields["research_model"].default == (config.OPENAI_MODEL or "gpt-4o-mini")
    # A blank OPENAI_MODEL must still produce a usable model name.
    assert Configuration.model_fields["research_model"].default


def test_model_fields_are_exactly_the_three_known_keys():
    assert list(Configuration.model_fields.keys()) == [
        "max_structured_output_retries",
        "research_model",
        "research_model_max_tokens",
    ]


def test_from_runnable_config_with_no_config_returns_defaults():
    assert Configuration.from_runnable_config() == Configuration()


def test_from_runnable_config_with_empty_config_returns_defaults():
    assert Configuration.from_runnable_config({}) == Configuration()
    assert Configuration.from_runnable_config({"configurable": {}}) == Configuration()
    assert Configuration.from_runnable_config({"not_configurable": {"research_model": "x"}}) == Configuration()


def test_from_runnable_config_merges_known_keys():
    merged = Configuration.from_runnable_config(
        {
            "configurable": {
                "max_structured_output_retries": 7,
                "research_model": "my-custom-model",
                "research_model_max_tokens": 256,
            }
        }
    )

    assert merged.max_structured_output_retries == 7
    assert merged.research_model == "my-custom-model"
    assert merged.research_model_max_tokens == 256


def test_from_runnable_config_ignores_unknown_and_none_keys():
    merged = Configuration.from_runnable_config(
        {
            "configurable": {
                "unknown_key": "ignored",
                "research_model": None,
                "max_structured_output_retries": None,
                "research_model_max_tokens": 128,
            }
        }
    )

    assert not hasattr(merged, "unknown_key")
    assert merged.research_model == Configuration().research_model
    assert merged.max_structured_output_retries == 3
    assert merged.research_model_max_tokens == 128
