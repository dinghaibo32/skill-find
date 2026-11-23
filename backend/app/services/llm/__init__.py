"""LLM integration layer.

Model calls go through the `LLMClient` protocol so routes and services
never depend on a concrete vendor SDK.
"""

from app.core.config import get_settings
from app.services.llm.base import (
    ChatMessage,
    ChatResult,
    LLMClient,
    LLMError,
    LLMNotConfiguredError,
    LLMUsage,
    ToolCall,
    ToolChatResult,
)
from app.services.llm.openai_compatible import OpenAICompatibleClient

__all__ = [
    "ChatMessage",
    "ChatResult",
    "LLMClient",
    "LLMError",
    "LLMNotConfiguredError",
    "LLMUsage",
    "OpenAICompatibleClient",
    "ToolCall",
    "ToolChatResult",
    "get_llm_client",
]


def get_llm_client() -> LLMClient:
    """Factory for the default LLM client, driven by settings."""
    settings = get_settings()
    return OpenAICompatibleClient(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
        input_price_per_million=settings.llm_input_price_per_million,
        output_price_per_million=settings.llm_output_price_per_million,
    )
