"""Tests for the openai-SDK based LLM client (no real network calls)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openai import APIConnectionError

from app.services.llm import openai_compatible
from app.services.llm.base import ChatMessage, LLMError, LLMNotConfiguredError
from app.services.llm.openai_compatible import OpenAICompatibleClient


def _response(content="hi", prompt_tokens=1000, completion_tokens=500, total_tokens=1500):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
    )


def _patch_sdk(monkeypatch, response=None, error=None):
    fake = MagicMock()
    if error is not None:
        fake.chat.completions.create = AsyncMock(side_effect=error)
    else:
        fake.chat.completions.create = AsyncMock(return_value=response)
    fake.close = AsyncMock()
    constructor = MagicMock(return_value=fake)
    monkeypatch.setattr(openai_compatible, "AsyncOpenAI", constructor)
    return fake, constructor


def _client(api_key="sk-test"):
    return OpenAICompatibleClient(
        api_key=api_key,
        base_url="https://example.com/v1",
        model="qwen-plus",
        input_price_per_million=0.8,
        output_price_per_million=2.0,
    )


def _chat(client):
    return asyncio.run(client.chat([ChatMessage(role="user", content="hello")]))


def test_chat_returns_content_and_usage(monkeypatch):
    fake, constructor = _patch_sdk(monkeypatch, response=_response())
    result = _chat(_client())
    assert result.content == "hi"
    assert result.model == "qwen-plus"
    assert result.usage.input_tokens == 1000
    assert result.usage.output_tokens == 500
    assert result.usage.total_tokens == 1500
    assert result.usage.cost == 0.0018
    fake.close.assert_awaited_once()
    constructor.assert_called_once_with(
        api_key="sk-test",
        base_url="https://example.com/v1",
        timeout=60.0,
    )
    kwargs = fake.chat.completions.create.await_args.kwargs
    assert kwargs["model"] == "qwen-plus"
    assert kwargs["messages"] == [{"role": "user", "content": "hello"}]


def test_cost_rounded_to_six_decimals(monkeypatch):
    _patch_sdk(
        monkeypatch,
        response=_response(prompt_tokens=12, completion_tokens=34, total_tokens=46),
    )
    result = _chat(_client())
    assert result.usage.cost == 0.000078


def test_total_tokens_fallback(monkeypatch):
    _patch_sdk(monkeypatch, response=_response(total_tokens=None))
    result = _chat(_client())
    assert result.usage.total_tokens == 1500


def test_zero_total_tokens_kept(monkeypatch):
    _patch_sdk(
        monkeypatch,
        response=_response(prompt_tokens=0, completion_tokens=0, total_tokens=0),
    )
    result = _chat(_client())
    assert result.usage.total_tokens == 0
    assert result.usage.cost == 0.0


def test_missing_usage_raises(monkeypatch):
    response = _response()
    response.usage = None
    _patch_sdk(monkeypatch, response=response)
    with pytest.raises(LLMError):
        _chat(_client())


def test_empty_choices_raises(monkeypatch):
    response = _response()
    response.choices = []
    _patch_sdk(monkeypatch, response=response)
    with pytest.raises(LLMError):
        _chat(_client())


def test_none_content_raises(monkeypatch):
    _patch_sdk(monkeypatch, response=_response(content=None))
    with pytest.raises(LLMError):
        _chat(_client())


def test_sdk_error_mapped_to_llm_error(monkeypatch):
    error = APIConnectionError(
        request=httpx.Request("POST", "https://example.com/v1/chat/completions")
    )
    fake, _ = _patch_sdk(monkeypatch, error=error)
    with pytest.raises(LLMError):
        _chat(_client())
    fake.close.assert_awaited_once()


def test_missing_api_key_raises():
    with pytest.raises(LLMNotConfiguredError):
        _chat(_client(api_key=""))
