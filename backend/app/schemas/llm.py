"""Schemas for the LLM chat endpoint."""

from typing import Literal

from pydantic import BaseModel, Field

from app.services.llm.base import LLMUsage


class PublicChatMessage(BaseModel):
    """Public API message: tool roles are internal to the agent loop."""

    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """Payload for POST /api/llm/chat."""

    messages: list[PublicChatMessage] = Field(min_length=1)


class ChatResponse(BaseModel):
    """Reply text plus per-call token and cost statistics."""

    reply: str
    model: str
    usage: LLMUsage
