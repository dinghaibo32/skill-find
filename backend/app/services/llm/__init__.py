"""LLM integration layer.

Future model calls go through the `LLMClient` protocol so routes and
services never depend on a concrete vendor SDK.
"""

from app.core.config import get_settings
from app.services.llm.base import ChatMessage, LLMClient, LLMError, LLMNotConfiguredError
from app.services.llm.openai_compatible import OpenAICompatibleClient

__all__ = [
    "ChatMessage",
    "LLMClient",
    "LLMError",
    "LLMNotConfiguredError",
    "OpenAICompatibleClient",
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
    )