"""Hermetic unit tests for the Shortlister agent Configuration model."""

from leadgen import config
from leadgen.agents.shortlister.configuration import Configuration


def test_configuration_defaults():
    settings = Configuration()

    assert settings.screener_market == "india"
    assert settings.screener_limit == 60
    assert settings.top_n_companies == 10
    assert settings.max_verifier_iterations == 15
    assert settings.max_concurrent_research_units == 20
    assert settings.max_react_tool_calls == 10
    assert settings.token_prune_limit == 350000
    assert settings.max_structured_output_retries == 3
    assert settings.per_million_input_tk_cost == 0.250
    assert settings.per_million_output_tk_cost == 2.000
    assert settings.query_model == (config.OPENAI_MODEL or "gpt-4o-mini")
    assert settings.verifier_model == (config.OPENAI_MODEL or "gpt-4o-mini")
    assert settings.compression_model == (config.OPENAI_MODEL or "gpt-4o-mini")


def test_from_runnable_config_merges_known_keys():
    settings = Configuration.from_runnable_config(
        {"configurable": {"top_n_companies": 3, "screener_market": "us"}}
    )

    assert settings.top_n_companies == 3
    assert settings.screener_market == "us"
    assert settings.screener_limit == 60


def test_from_runnable_config_ignores_unknown_keys():
    settings = Configuration.from_runnable_config(
        {"configurable": {"not_a_real_field": "ignored", "top_n_companies": 4}}
    )

    assert settings.top_n_companies == 4
    assert not hasattr(settings, "not_a_real_field")


def test_from_runnable_config_ignores_none_values():
    settings = Configuration.from_runnable_config(
        {"configurable": {"top_n_companies": None, "screener_limit": 7}}
    )

    assert settings.top_n_companies == 10
    assert settings.screener_limit == 7


def test_from_runnable_config_empty_config_uses_defaults():
    assert Configuration.from_runnable_config({}).top_n_companies == 10
    assert Configuration.from_runnable_config(None).top_n_companies == 10
    assert Configuration.from_runnable_config({"configurable": {}}).top_n_companies == 10
