"""Tests for path-traversal-safe skill file reading."""

import pytest

from app.services.skills.files import SkillFileError, read_skill_file
from app.services.skills.models import SkillRecord


def _record(tmp_path) -> SkillRecord:
    skill_dir = tmp_path / "demo"
    (skill_dir / "templates").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: d\n---\nbody\n", encoding="utf-8"
    )
    (skill_dir / "templates" / "t.md").write_text("template content", encoding="utf-8")
    return SkillRecord(
        name="demo", description="d", source_dir="skills",
        skill_path=str(skill_dir / "SKILL.md"),
    )


def test_read_valid_relative_path(tmp_path):
    record = _record(tmp_path)
    assert read_skill_file(record, "templates/t.md") == "template content"


def test_reject_parent_traversal(tmp_path):
    record = _record(tmp_path)
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    with pytest.raises(SkillFileError, match="escapes"):
        read_skill_file(record, "../secret.txt")


def test_reject_nested_traversal(tmp_path):
    record = _record(tmp_path)
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    with pytest.raises(SkillFileError, match="escapes"):
        read_skill_file(record, "templates/../../secret.txt")


def test_reject_absolute_path(tmp_path):
    record = _record(tmp_path)
    with pytest.raises(SkillFileError, match="absolute"):
        read_skill_file(record, str(tmp_path / "secret.txt"))


def test_reject_missing_file(tmp_path):
    record = _record(tmp_path)
    with pytest.raises(SkillFileError, match="not found"):
        read_skill_file(record, "nope.md")


def test_reject_oversized_file(tmp_path):
    record = _record(tmp_path)
    big = tmp_path / "demo" / "big.txt"
    big.write_text("x" * (51 * 1024), encoding="utf-8")
    with pytest.raises(SkillFileError, match="50KB"):
        read_skill_file(record, "big.txt")


def test_reject_non_utf8_file(tmp_path):
    record = _record(tmp_path)
    gbk = tmp_path / "demo" / "gbk.txt"
    gbk.write_bytes("中文内容".encode("gbk"))
    with pytest.raises(SkillFileError, match="UTF-8"):
        read_skill_file(record, "gbk.txt")


def test_read_exactly_50kb_allowed(tmp_path):
    record = _record(tmp_path)
    exact = tmp_path / "demo" / "exact.txt"
    exact.write_bytes(b"x" * (50 * 1024))
    assert len(read_skill_file(record, "exact.txt")) == 50 * 1024
