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


def test_skill_settings_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.skill_dirs == ["skills", "skills-extra"]
    assert settings.skill_injection_token_budget == 2000
    assert settings.skill_desc_truncate_chars == 80
    assert settings.agent_max_tool_rounds == 8


def test_repo_root_points_to_workspace() -> None:
    from app.core.config import get_repo_root

    assert (get_repo_root() / "skills").is_dir()
    assert (get_repo_root() / "evals" / "routing-eval.jsonl").is_file()
