"""Skill listing, rescan and debug simulate endpoints."""

from fastapi import APIRouter, Depends

from app.schemas.skills import InjectionInfo, SkillInfo, SkillsResponse, SimulateRequest
from app.services.skills.agent import AgentService, get_agent_service
from app.services.skills.injector import build_injection, count_tokens, skill_line
from app.services.skills.registry import SkillRegistry, get_registry

router = APIRouter(tags=["skills"])


def _build_response(
    registry: SkillRegistry, agent: AgentService, session_id: str | None
) -> SkillsResponse:
    records = registry.records
    injection = build_injection(records, registry.budget, registry.truncate_chars)
    loaded = agent.loaded_skills(session_id) if session_id else set()
    skills = [
        SkillInfo(
            name=r.name,
            description=r.description,
            source_dir=r.source_dir,
            status=r.status,
            overridden_by=r.overridden_by,
            tokens=count_tokens(skill_line(r)),
            loaded=r.name in loaded,
        )
        for r in records
    ]
    return SkillsResponse(
        skills=skills,
        injection=InjectionInfo(
            tokens=injection.tokens,
            budget=injection.budget,
            strategy=injection.strategy,
            skill_count=injection.skill_count,
        ),
        issues=registry.issues,
    )


@router.get("/skills", response_model=SkillsResponse)
async def list_skills(
    session_id: str | None = None,
    registry: SkillRegistry = Depends(get_registry),
    agent: AgentService = Depends(get_agent_service),
) -> SkillsResponse:
    """List skills with injection stats; loaded flags require session_id."""
    registry.refresh()
    return _build_response(registry, agent, session_id)


@router.post("/skills/rescan", response_model=SkillsResponse)
async def rescan_skills(
    session_id: str | None = None,
    registry: SkillRegistry = Depends(get_registry),
    agent: AgentService = Depends(get_agent_service),
) -> SkillsResponse:
    """Force a full rescan of skill directories, ignoring mtime caching."""
    registry.force_rescan()
    return _build_response(registry, agent, session_id)


@router.post("/debug/simulate", response_model=SkillsResponse)
async def toggle_simulate(
    request: SimulateRequest,
    session_id: str | None = None,
    registry: SkillRegistry = Depends(get_registry),
    agent: AgentService = Depends(get_agent_service),
) -> SkillsResponse:
    """Toggle degraded-injection simulation for debugging."""
    registry.set_simulate(request.enabled)
    return _build_response(registry, agent, session_id)
