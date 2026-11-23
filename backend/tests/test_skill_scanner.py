"""Tests for skill scanning: parsing, fault tolerance, conflict resolution."""

from pathlib import Path

import pytest

from app.core.config import get_repo_root
from app.services.skills.scanner import SkillParseError, parse_skill_file, scan_directories


def _write_skill(root: Path, name: str, description: str = "demo description") -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    path = skill_dir / "SKILL.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# Body of {name}\n",
        encoding="utf-8",
    )
    return path


def test_parse_valid_frontmatter(tmp_path):
    path = _write_skill(tmp_path, "demo")
    name, description, body = parse_skill_file(path)
    assert name == "demo"
    assert description == "demo description"
    assert body == "# Body of demo"


def test_parse_missing_closing_delimiter(tmp_path):
    path = tmp_path / "SKILL.md"
    path.write_text("---\nname: x\ndescription: y\n\n# no closing\n", encoding="utf-8")
    with pytest.raises(SkillParseError, match="closing"):
        parse_skill_file(path)


def test_parse_missing_opening_delimiter(tmp_path):
    path = tmp_path / "SKILL.md"
    path.write_text("# just markdown\n", encoding="utf-8")
    with pytest.raises(SkillParseError, match="opening"):
        parse_skill_file(path)


def test_parse_missing_name_field(tmp_path):
    path = tmp_path / "SKILL.md"
    path.write_text("---\ndescription: y\n---\nbody\n", encoding="utf-8")
    with pytest.raises(SkillParseError, match="name"):
        parse_skill_file(path)


def test_parse_invalid_yaml(tmp_path):
    path = tmp_path / "SKILL.md"
    path.write_text("---\nname: [unclosed\n---\nbody\n", encoding="utf-8")
    with pytest.raises(SkillParseError, match="YAML"):
        parse_skill_file(path)


def test_scan_skips_broken_and_reports_reason(tmp_path):
    _write_skill(tmp_path, "good")
    broken_dir = tmp_path / "broken"
    broken_dir.mkdir()
    (broken_dir / "SKILL.md").write_text("---\nname: broken\n", encoding="utf-8")
    result = scan_directories([tmp_path])
    assert [r.name for r in result.skills] == ["good"]
    assert len(result.issues) == 1
    assert "broken" in result.issues[0].path
    assert "closing" in result.issues[0].reason


def test_scan_conflict_first_dir_wins(tmp_path):
    primary = tmp_path / "primary"
    secondary = tmp_path / "secondary"
    _write_skill(primary, "dup", description="primary version")
    _write_skill(secondary, "dup", description="secondary version")
    result = scan_directories([primary, secondary])
    assert len(result.skills) == 2
    winner, loser = result.skills
    assert winner.status == "active"
    assert winner.description == "primary version"
    assert loser.status == "overridden"
    assert loser.overridden_by == "primary"
    assert loser.source_dir == "secondary"


def test_scan_missing_directory_reports_issue(tmp_path):
    result = scan_directories([tmp_path / "nope"])
    assert result.skills == []
    assert len(result.issues) == 1
    assert "does not exist" in result.issues[0].reason


def test_scan_real_fixtures():
    result = scan_directories([get_repo_root() / "skills", get_repo_root() / "skills-extra"])
    active = [r for r in result.skills if r.status == "active"]
    assert len(active) == 6
    overridden = [r for r in result.skills if r.status == "overridden"]
    assert len(overridden) == 1
    assert overridden[0].name == "short-drama-script"
    assert overridden[0].source_dir == "skills-extra"
    assert overridden[0].overridden_by == "skills"
    assert any("broken-frontmatter-demo" in i.path for i in result.issues)
