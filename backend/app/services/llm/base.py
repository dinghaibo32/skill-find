"""Vendor-agnostic LLM contracts.

Define the message shape and the client protocol here; concrete
implementations (OpenAI-compatible, local models, mocks) live alongside.
"""

from typing import Literal, Protocol

from pydantic import BaseModel


class ToolCall(BaseModel):
    """A function call requested by the model. arguments is a raw JSON string."""

    id: str
    name: str
    arguments: str


class ChatMessage(BaseModel):
    """A single chat turn sent to the model, including tool exchanges."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None


class LLMUsage(BaseModel):
    """Token counts and cost for a single LLM call. Cost is in CNY."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float


class ToolChatResult(BaseModel):
    """Reply or tool calls, plus per-call usage statistics."""

    content: str | None
    tool_calls: list[ToolCall]
    model: str
    usage: LLMUsage


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

    async def chat_with_tools(
        self, messages: list[ChatMessage], tools: list[dict]
    ) -> ToolChatResult:
        """Send messages with tool definitions; return reply or tool calls."""
        ...
