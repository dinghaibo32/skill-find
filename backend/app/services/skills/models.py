"""Data models shared across the skill system."""

from typing import Literal

from pydantic import BaseModel


class SkillRecord(BaseModel):
    """One scanned skill. Overridden records keep their own source path."""

    name: str
    description: str
    source_dir: str
    skill_path: str
    status: Literal["active", "overridden"] = "active"
    overridden_by: str | None = None
    mtime: float = 0.0


class ScanIssue(BaseModel):
    """A skipped candidate with a human-readable reason."""

    path: str
    reason: str


class ScanResult(BaseModel):
    skills: list[SkillRecord]
    issues: list[ScanIssue]


class InjectionResult(BaseModel):
    """System-prompt injection text with token accounting."""

    text: str
    tokens: int
    strategy: Literal["full", "truncated", "names_only"]
    budget: int
    skill_count: int


class AgentEvent(BaseModel):
    """One tool execution inside an agent turn."""

    type: Literal["load_skill", "read_skill_file"]
    skill: str
    path: str | None = None
    ok: bool
    error: str | None = None
