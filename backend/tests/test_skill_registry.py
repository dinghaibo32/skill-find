"""Tests for registry hot reload and the synthetic skill overlay."""

import os

from app.services.skills.registry import SkillRegistry


def _write_skill(root, name, description="old description"):
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    path = skill_dir / "SKILL.md"
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name} body\n",
        encoding="utf-8",
    )
    return path


def _registry(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(exist_ok=True)
    return SkillRegistry(dirs=[skills_dir], budget=2000, truncate_chars=80)


def test_refresh_picks_up_modified_skill(tmp_path):
    path = _write_skill(tmp_path / "skills", "demo")
    registry = _registry(tmp_path)
    assert registry.get_active("demo").description == "old description"
    _write_skill(tmp_path / "skills", "demo", description="new description")
    stat = path.stat()
    os.utime(path, (stat.st_atime + 10, stat.st_mtime + 10))
    registry.refresh()
    assert registry.get_active("demo").description == "new description"


def test_refresh_picks_up_added_and_deleted_skills(tmp_path):
    _write_skill(tmp_path / "skills", "a")
    registry = _registry(tmp_path)
    assert len(registry.records) == 1
    _write_skill(tmp_path / "skills", "b")
    registry.refresh()
    assert {r.name for r in registry.records} == {"a", "b"}
    (tmp_path / "skills" / "a" / "SKILL.md").unlink()
    registry.refresh()
    assert {r.name for r in registry.records} == {"b"}


def test_simulate_overlay_adds_and_removes_200(tmp_path):
    _write_skill(tmp_path / "skills", "a")
    registry = _registry(tmp_path)
    registry.set_simulate(True)
    assert len(registry.records) == 201
    synthetic = [r for r in registry.records if r.source_dir == "synthetic"]
    assert len(synthetic) == 200
    assert synthetic[0].name == "demo-skill-001"
    registry.set_simulate(False)
    assert len(registry.records) == 1


def test_load_body_real_and_synthetic(tmp_path):
    _write_skill(tmp_path / "skills", "a")
    registry = _registry(tmp_path)
    assert registry.load_body(registry.get_active("a")) == "# a body"
    registry.set_simulate(True)
    body = registry.load_body(registry.get_active("demo-skill-001"))
    assert "demo-skill-001" in body


def test_get_active_unknown_returns_none(tmp_path):
    registry = _registry(tmp_path)
    assert registry.get_active("nope") is None


def test_force_rescan_updates_broken_issue(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    broken = skills_dir / "broken"
    broken.mkdir()
    (broken / "SKILL.md").write_text("---\nname: broken\n", encoding="utf-8")
    registry = SkillRegistry(dirs=[skills_dir], budget=2000, truncate_chars=80)
    assert len(registry.issues) == 1
    _write_skill(skills_dir, "broken", description="fixed")
    registry.force_rescan()
    assert registry.issues == []
    assert registry.get_active("broken") is not None


def test_refresh_survives_stat_error(tmp_path, monkeypatch):
    _write_skill(tmp_path / "skills", "a")
    registry = _registry(tmp_path)
    from pathlib import Path

    original_stat = Path.stat

    def flaky_stat(self, *args, **kwargs):
        if self.name == "SKILL.md":
            raise FileNotFoundError("deleted mid-snapshot")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky_stat)
    registry.refresh()  # must not raise


def test_refresh_skips_rescan_when_unchanged(tmp_path, monkeypatch):
    _write_skill(tmp_path / "skills", "a")
    registry = _registry(tmp_path)
    import app.services.skills.registry as mod

    calls = []
    monkeypatch.setattr(mod, "scan_directories", lambda dirs: calls.append(1))
    registry.refresh()
    registry.refresh()
    assert calls == []
