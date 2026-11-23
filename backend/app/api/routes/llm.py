"""LLM chat endpoint exposing the service-layer client."""

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.llm import ChatRequest, ChatResponse
from app.services.llm import get_llm_client
from app.services.llm.base import LLMClient, LLMError, LLMNotConfiguredError

router = APIRouter(tags=["llm"])


@router.post("/llm/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    client: LLMClient = Depends(get_llm_client),
) -> ChatResponse:
    """Send messages to the configured model and return reply with usage."""
    try:
        result = await client.chat(request.messages)
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ChatResponse(reply=result.content, model=result.model, usage=result.usage)
