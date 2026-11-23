"""Skill registry: mtime-based hot reload plus a synthetic overlay.

refresh() is cheap (stat calls only) and runs before every agent turn,
so file edits take effect on the next turn without a restart.
"""

from pathlib import Path

from app.core.config import get_repo_root, get_settings
from app.services.skills.models import ScanIssue, ScanResult, SkillRecord
from app.services.skills.scanner import parse_skill_file, scan_directories

SYNTHETIC_SOURCE = "synthetic"


def synthetic_skills(count: int = 200) -> list[SkillRecord]:
    """Deterministic in-memory skills used to demo injection length control."""
    return [
        SkillRecord(
            name=f"demo-skill-{i:03d}",
            description=(
                f"Simulated skill #{i}: handles demo task type {i}, "
                "used to showcase injection length control with many skills."
            ),
            source_dir=SYNTHETIC_SOURCE,
            skill_path=f"<synthetic>/demo-skill-{i:03d}/SKILL.md",
        )
        for i in range(1, count + 1)
    ]


class SkillRegistry:
    def __init__(self, dirs: list[Path], budget: int, truncate_chars: int) -> None:
        self._dirs = dirs
        self.budget = budget
        self.truncate_chars = truncate_chars
        self._scan = ScanResult(skills=[], issues=[])
        self._snapshot: dict[str, float] = {}
        self._simulate = False
        self.force_rescan()

    @property
    def records(self) -> list[SkillRecord]:
        if self._simulate:
            return self._scan.skills + synthetic_skills()
        return self._scan.skills

    @property
    def issues(self) -> list[ScanIssue]:
        return self._scan.issues

    def get_active(self, name: str) -> SkillRecord | None:
        for record in self.records:
            if record.name == name and record.status == "active":
                return record
        return None

    def load_body(self, record: SkillRecord) -> str:
        if record.source_dir == SYNTHETIC_SOURCE:
            return (
                f"# {record.name}\n\n"
                "This is a simulated skill body for injection-length demos."
            )
        _, _, body = parse_skill_file(Path(record.skill_path))
        return body

    def set_simulate(self, enabled: bool) -> None:
        self._simulate = enabled

    def refresh(self) -> None:
        """Rescan only when the SKILL.md mtime snapshot changed."""
        snapshot = self._current_snapshot()
        if snapshot != self._snapshot:
            self._scan = scan_directories(self._dirs)
            self._snapshot = snapshot

    def force_rescan(self) -> None:
        self._scan = scan_directories(self._dirs)
        self._snapshot = self._current_snapshot()

    def _current_snapshot(self) -> dict[str, float]:
        snapshot: dict[str, float] = {}
        for directory in self._dirs:
            if not directory.is_dir():
                continue
            for child in sorted(directory.iterdir()):
                skill_file = child / "SKILL.md"
                if skill_file.is_file():
                    snapshot[str(skill_file)] = skill_file.stat().st_mtime
        return snapshot


_registry: SkillRegistry | None = None


def get_registry() -> SkillRegistry:
    """Process-wide singleton, used as a FastAPI dependency."""
    global _registry
    if _registry is None:
        settings = get_settings()
        root = get_repo_root()
        _registry = SkillRegistry(
            dirs=[root / d for d in settings.skill_dirs],
            budget=settings.skill_injection_token_budget,
            truncate_chars=settings.skill_desc_truncate_chars,
        )
    return _registry
