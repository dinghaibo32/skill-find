"""Agent chat endpoint running the tool-calling loop."""

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.skills import AgentChatRequest, AgentChatResponse
from app.services.llm.base import LLMError, LLMNotConfiguredError
from app.services.skills.agent import AgentService, get_agent_service

router = APIRouter(tags=["agent"])


@router.post("/agent/chat", response_model=AgentChatResponse)
async def agent_chat(
    request: AgentChatRequest,
    agent: AgentService = Depends(get_agent_service),
) -> AgentChatResponse:
    try:
        result = await agent.run_turn(request.session_id, request.message)
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return AgentChatResponse(
        reply=result.reply,
        events=result.events,
        usage=result.usage,
        injection_tokens=result.injection_tokens,
        tool_rounds=result.tool_rounds,
    )
