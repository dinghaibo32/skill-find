"""Tests for chat_with_tools on the openai-SDK client (no real network)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import APIConnectionError
import httpx

from app.services.llm import openai_compatible
from app.services.llm.base import ChatMessage, LLMError, LLMNotConfiguredError, ToolCall
from app.services.llm.openai_compatible import OpenAICompatibleClient


def _tool_call(id="call_1", name="load_skill", arguments='{"name": "demo"}'):
    return SimpleNamespace(id=id, function=SimpleNamespace(name=name, arguments=arguments))


def _response(content=None, tool_calls=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150),
    )


def _patch_sdk(monkeypatch, response=None, error=None):
    fake = MagicMock()
    if error is not None:
        fake.chat.completions.create = AsyncMock(side_effect=error)
    else:
        fake.chat.completions.create = AsyncMock(return_value=response)
    fake.close = AsyncMock()
    monkeypatch.setattr(openai_compatible, "AsyncOpenAI", MagicMock(return_value=fake))
    return fake


def _client(api_key="sk-test"):
    return OpenAICompatibleClient(
        api_key=api_key,
        base_url="https://example.com/v1",
        model="qwen-plus",
        input_price_per_million=0.8,
        output_price_per_million=2.0,
    )


_TOOLS = [{"type": "function", "function": {"name": "load_skill", "parameters": {}}}]


def _run(client, messages):
    return asyncio.run(client.chat_with_tools(messages, _TOOLS))


def test_returns_tool_calls_and_usage(monkeypatch):
    fake = _patch_sdk(monkeypatch, response=_response(tool_calls=[_tool_call()]))
    result = _run(_client(), [ChatMessage(role="user", content="hi")])
    assert result.content is None
    assert result.tool_calls == [ToolCall(id="call_1", name="load_skill", arguments='{"name": "demo"}')]
    assert result.usage.input_tokens == 100
    assert result.usage.cost == 0.00018
    fake.close.assert_awaited_once()
    kwargs = fake.chat.completions.create.await_args.kwargs
    assert kwargs["tools"] == _TOOLS


def test_plain_reply_has_empty_tool_calls(monkeypatch):
    _patch_sdk(monkeypatch, response=_response(content="done"))
    result = _run(_client(), [ChatMessage(role="user", content="hi")])
    assert result.content == "done"
    assert result.tool_calls == []


def test_tool_message_payload_shape(monkeypatch):
    fake = _patch_sdk(monkeypatch, response=_response(content="final"))
    messages = [
        ChatMessage(role="user", content="hi"),
        ChatMessage(
            role="assistant", content="",
            tool_calls=[ToolCall(id="call_1", name="load_skill", arguments='{"name": "demo"}')],
        ),
        ChatMessage(role="tool", content="body text", tool_call_id="call_1"),
    ]
    _run(_client(), messages)
    payload = fake.chat.completions.create.await_args.kwargs["messages"]
    assert payload[0] == {"role": "user", "content": "hi"}
    assert payload[1] == {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": "load_skill", "arguments": '{"name": "demo"}'}}
        ],
    }
    assert payload[2] == {"role": "tool", "content": "body text", "tool_call_id": "call_1"}


def test_plain_chat_payload_unchanged(monkeypatch):
    fake = _patch_sdk(monkeypatch, response=_response(content="hello"))
    asyncio.run(_client().chat([ChatMessage(role="user", content="hello")]))
    payload = fake.chat.completions.create.await_args.kwargs["messages"]
    assert payload == [{"role": "user", "content": "hello"}]


def test_missing_key_raises():
    with pytest.raises(LLMNotConfiguredError):
        _run(_client(api_key=""), [ChatMessage(role="user", content="hi")])


def test_api_error_mapped(monkeypatch):
    error = APIConnectionError(request=httpx.Request("POST", "https://example.com/v1"))
    fake = _patch_sdk(monkeypatch, error=error)
    with pytest.raises(LLMError):
        _run(_client(), [ChatMessage(role="user", content="hi")])
    fake.close.assert_awaited_once()


def test_missing_usage_raises(monkeypatch):
    response = _response(content="done")
    response.usage = None
    _patch_sdk(monkeypatch, response=response)
    with pytest.raises(LLMError):
        _run(_client(), [ChatMessage(role="user", content="hi")])


def test_content_and_tool_calls_coexist(monkeypatch):
    _patch_sdk(monkeypatch, response=_response(content="let me check", tool_calls=[_tool_call()]))
    result = _run(_client(), [ChatMessage(role="user", content="hi")])
    assert result.content == "let me check"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "load_skill"
