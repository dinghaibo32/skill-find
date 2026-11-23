"""Tests for the settings-driven LLM client factory."""

from app.core.config import Settings
from app.services import llm
from app.services.llm.openai_compatible import OpenAICompatibleClient


def test_factory_uses_settings(monkeypatch):
    settings = Settings(
        _env_file=None,
        llm_api_key="sk-test",
        llm_base_url="https://example.com/v1",
        llm_model="qwen-max",
        llm_input_price_per_million=2.4,
        llm_output_price_per_million=9.6,
    )
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    client = llm.get_llm_client()
    assert isinstance(client, OpenAICompatibleClient)
    assert client._model == "qwen-max"
    assert client._input_price == 2.4
    assert client._output_price == 9.6
