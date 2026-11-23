"""Tests for LLM contract models."""

from app.services.llm.base import ChatResult, LLMUsage


def test_llm_usage_fields() -> None:
    usage = LLMUsage(input_tokens=12, output_tokens=34, total_tokens=46, cost=0.000078)
    assert usage.total_tokens == 46
    assert usage.cost == 0.000078


def test_chat_result_fields() -> None:
    result = ChatResult(
        content="hello",
        model="qwen-plus",
        usage=LLMUsage(input_tokens=1, output_tokens=2, total_tokens=3, cost=0.0),
    )
    assert result.content == "hello"
    assert result.model == "qwen-plus"
    assert result.usage.output_tokens == 2
