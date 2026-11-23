"""Tests for LLM-related settings."""

from app.core.config import Settings


def test_llm_price_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.llm_input_price_per_million == 0.8
    assert settings.llm_output_price_per_million == 2.0


def test_llm_prices_overridable() -> None:
    settings = Settings(
        _env_file=None,
        llm_input_price_per_million=1.5,
        llm_output_price_per_million=6.0,
    )
    assert settings.llm_input_price_per_million == 1.5
    assert settings.llm_output_price_per_million == 6.0
