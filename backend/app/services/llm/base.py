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


class LLMUsage(BaseModel):
    """Token counts and cost for a single LLM call. Cost is in CNY."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float


class ChatResult(BaseModel):
    """Assistant reply plus per-call usage statistics."""

    content: str
    model: str
    usage: LLMUsage


class LLMError(Exception):
    """Base error for LLM call failures."""


class LLMNotConfiguredError(LLMError):
    """Raised when an LLM call is attempted without an API key configured."""


class LLMClient(Protocol):
    """Minimal contract every LLM implementation must satisfy."""

    async def chat(self, messages: list[ChatMessage]) -> ChatResult:
        """Send chat messages and return the reply with usage statistics."""
        ...