"""Schemas for skill listing, agent chat and debug endpoints."""

from pydantic import BaseModel, Field

from app.services.llm.base import LLMUsage
from app.services.skills.models import AgentEvent, ScanIssue


class SkillInfo(BaseModel):
    name: str
    description: str
    source_dir: str
    status: str
    overridden_by: str | None
    tokens: int
    loaded: bool


class InjectionInfo(BaseModel):
    tokens: int
    budget: int
    strategy: str
    skill_count: int


class SkillsResponse(BaseModel):
    skills: list[SkillInfo]
    injection: InjectionInfo
    issues: list[ScanIssue]
    simulating: bool


class SimulateRequest(BaseModel):
    enabled: bool


class AgentChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class AgentChatResponse(BaseModel):
    reply: str
    events: list[AgentEvent]
    usage: LLMUsage
    injection_tokens: int
    tool_rounds: int
