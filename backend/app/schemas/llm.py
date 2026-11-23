"""Schemas for the LLM chat endpoint."""

from pydantic import BaseModel, Field

from app.services.llm.base import ChatMessage, LLMUsage


class ChatRequest(BaseModel):
    """Payload for POST /api/llm/chat."""

    messages: list[ChatMessage] = Field(min_length=1)


class ChatResponse(BaseModel):
    """Reply text plus per-call token and cost statistics."""

    reply: str
    model: str
    usage: LLMUsage
