"""Read skill companion files without escaping the skill directory."""

from pathlib import Path

from app.services.skills.models import SkillRecord

MAX_FILE_BYTES = 50 * 1024


class SkillFileError(Exception):
    """Raised when a companion file cannot be safely read."""


def read_skill_file(record: SkillRecord, path: str) -> str:
    """Resolve path inside the skill root; reject traversal and oversized files."""
    if Path(path).is_absolute():
        raise SkillFileError("absolute paths are not allowed")
    root = Path(record.skill_path).parent.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise SkillFileError("path escapes the skill directory")
    if not target.is_file():
        raise SkillFileError(f"file not found: {path}")
    if target.stat().st_size > MAX_FILE_BYTES:
        raise SkillFileError("file exceeds 50KB limit")
    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SkillFileError(f"file is not UTF-8 text: {path}") from exc
    except OSError as exc:
        raise SkillFileError(f"cannot read file {path}: {exc}") from exc
