"""Directory scanning with frontmatter parsing and conflict resolution."""

from pathlib import Path

import yaml

from app.services.skills.models import ScanIssue, ScanResult, SkillRecord


class SkillParseError(ValueError):
    """Raised when a SKILL.md frontmatter is invalid."""


def parse_skill_file(path: Path) -> tuple[str, str, str]:
    """Return (name, description, body). Raise SkillParseError when invalid."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].rstrip() != "---":
        raise SkillParseError("missing opening '---' frontmatter delimiter")
    end = None
    for index in range(1, len(lines)):
        if lines[index].rstrip() == "---":
            end = index
            break
    if end is None:
        raise SkillParseError("missing closing '---' frontmatter delimiter")
    try:
        meta = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as exc:
        raise SkillParseError(f"invalid YAML frontmatter: {exc}") from exc
    if not isinstance(meta, dict):
        raise SkillParseError("frontmatter is not a mapping")
    name = meta.get("name")
    description = meta.get("description")
    if not isinstance(name, str) or not name.strip():
        raise SkillParseError("frontmatter field 'name' must be a non-empty string")
    if not isinstance(description, str) or not description.strip():
        raise SkillParseError("frontmatter field 'description' must be a non-empty string")
    body = "\n".join(lines[end + 1 :]).strip()
    return name.strip(), description.strip(), body


def scan_directories(dirs: list[Path]) -> ScanResult:
    """Scan dirs in priority order; first registration wins name conflicts.

    A broken candidate is skipped with a ScanIssue and never aborts the scan.
    """
    skills: list[SkillRecord] = []
    issues: list[ScanIssue] = []
    winners: dict[str, SkillRecord] = {}
    for directory in dirs:
        if not directory.is_dir():
            issues.append(ScanIssue(path=str(directory), reason="skill directory does not exist"))
            continue
        try:
            children = sorted(directory.iterdir())
        except OSError as exc:
            issues.append(ScanIssue(path=str(directory), reason=str(exc)))
            continue
        for child in children:
            if not child.is_dir():
                continue
            skill_file = child / "SKILL.md"
            try:
                # is_file() may re-raise OSError (e.g. race with deletion), so
                # keep it inside the guarded block to never abort the scan.
                if not skill_file.is_file():
                    issues.append(ScanIssue(path=str(child), reason="SKILL.md not found"))
                    continue
                mtime = skill_file.stat().st_mtime
                name, description, _ = parse_skill_file(skill_file)
            except (SkillParseError, OSError, UnicodeDecodeError) as exc:
                issues.append(ScanIssue(path=str(skill_file), reason=str(exc)))
                continue
            record = SkillRecord(
                name=name,
                description=description,
                source_dir=directory.name,
                skill_path=str(skill_file),
                mtime=mtime,
            )
            if name in winners:
                record.status = "overridden"
                record.overridden_by = winners[name].source_dir
            else:
                winners[name] = record
            skills.append(record)
    return ScanResult(skills=skills, issues=issues)
