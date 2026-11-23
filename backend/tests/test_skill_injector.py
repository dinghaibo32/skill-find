"""Tests for injection text building and budget degradation."""

from app.services.skills.injector import build_injection, count_tokens
from app.services.skills.models import SkillRecord


def _record(name: str, description: str = "d" * 50) -> SkillRecord:
    return SkillRecord(
        name=name,
        description=description,
        source_dir="skills",
        skill_path=f"/x/{name}/SKILL.md",
    )


def test_count_tokens_positive():
    assert count_tokens("hello world, this is a skill description") > 0


def test_full_strategy_within_budget():
    result = build_injection([_record("a"), _record("b")], budget=1000, truncate_chars=80)
    assert result.strategy == "full"
    assert "- a: " in result.text
    assert result.tokens <= 1000
    assert result.skill_count == 2


def test_truncated_strategy_when_full_exceeds_budget():
    records = [_record(f"s{i}", description="x" * 200) for i in range(10)]
    full_text = "\n".join(f"- {r.name}: {r.description}" for r in records)
    budget = count_tokens(full_text) - 1
    result = build_injection(records, budget=budget, truncate_chars=20)
    assert result.strategy == "truncated"
    assert result.tokens <= budget
    assert "…" in result.text


def test_names_only_strategy_when_truncated_still_exceeds():
    records = [_record(f"skill-{i}", description="x" * 200) for i in range(50)]
    result = build_injection(records, budget=10, truncate_chars=20)
    assert result.strategy == "names_only"
    assert ":" not in result.text
    assert "- skill-0" in result.text


def test_overridden_records_excluded():
    records = [
        _record("a"),
        SkillRecord(
            name="a",
            description="dup",
            source_dir="extra",
            skill_path="/y/a/SKILL.md",
            status="overridden",
            overridden_by="skills",
        ),
    ]
    result = build_injection(records, budget=1000, truncate_chars=80)
    assert result.skill_count == 1
    assert result.text.count("- a:") == 1


def test_full_strategy_at_exact_budget_boundary():
    records = [_record("a"), _record("b")]
    full_text = "\n".join(f"- {r.name}: {r.description}" for r in records)
    result = build_injection(records, budget=count_tokens(full_text), truncate_chars=80)
    assert result.strategy == "full"
