"""Vendor-agnostic LLM contracts.

Define the message shape and the client protocol here; concrete
implementations (OpenAI-compatible, local models, mocks) live alongside.
"""

from typing import Literal, Protocol

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """A single chat turn sent to the model."""

    role: Literal["system", "user", "assistant"]
    content: str


class LLMError(Exception):
    """Base error for LLM call failures."""


class LLMNotConfiguredError(LLMError):
    """Raised when an LLM call is attempted without an API key configured."""


class LLMClient(Protocol):
    """Minimal contract every LLM implementation must satisfy."""

    async def chat(self, messages: list[ChatMessage]) -> str:
        """Send chat messages and return the assistant reply text."""
        ...