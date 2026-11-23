"""Tests for routing eval scoring and fault tolerance."""

import asyncio
import json

from app.services.llm.base import LLMError
from app.services.skills.evals import EvalActual, EvalService, parse_actual, score
from app.services.skills.registry import SkillRegistry
from fakes import FakeLLM


def _registry(tmp_path) -> SkillRegistry:
    skill_dir = tmp_path / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo skill\n---\nbody\n", encoding="utf-8"
    )
    return SkillRegistry(dirs=[tmp_path / "skills"], budget=2000, truncate_chars=80)


def _eval_file(tmp_path):
    cases = [
        {"id": 1, "query": "q1", "expected_skill": "demo", "category": "normal"},
        {"id": 2, "query": "q2", "expected_skill": None, "category": "ambiguous"},
        {"id": 3, "query": "q3", "expected_skill": None, "category": "hard-negative"},
        {"id": 4, "query": "q4", "expected_skill": "demo", "category": "boundary"},
    ]
    path = tmp_path / "eval.jsonl"
    path.write_text("\n".join(json.dumps(c) for c in cases) + "\n", encoding="utf-8")
    return path


def test_scoring_rules():
    assert score("normal", "demo", EvalActual(action="load", skill="demo")) is True
    assert score("normal", "demo", EvalActual(action="load", skill="other")) is False
    assert score("boundary", "demo", EvalActual(action="clarify")) is False
    assert score("ambiguous", None, EvalActual(action="clarify")) is True
    assert score("ambiguous", None, EvalActual(action="load", skill="demo")) is False
    assert score("hard-negative", None, EvalActual(action="none")) is True
    assert score("no-skill", None, EvalActual(action="load", skill="demo")) is False


def test_parse_actual_plain_and_fenced():
    assert parse_actual('{"action": "load", "skill": "demo"}').skill == "demo"
    fenced = '```json\n{"action": "none", "skill": null}\n```'
    assert parse_actual(fenced).action == "none"


def test_parse_actual_extracts_first_json_object():
    # Regression: multiple JSON objects or trailing noise with '}' must not
    # turn a scoreable reply into an error.
    multi = '{"action":"load","skill":"demo"}\n{"action":"none"}'
    actual = parse_actual(multi)
    assert actual.action == "load"
    assert actual.skill == "demo"
    noisy = '{"action":"load","skill":"demo"} trailing {x}'
    actual = parse_actual(noisy)
    assert actual.action == "load"
    assert actual.skill == "demo"


def test_parse_actual_invalid_action_raises():
    import pytest

    with pytest.raises(ValueError):
        parse_actual('{"action": "jump"}')


def test_run_all_pass_and_cached(tmp_path):
    fake = FakeLLM(chat_replies=[
        '{"action": "load", "skill": "demo"}',
        '{"action": "clarify", "skill": null}',
        '{"action": "none", "skill": null}',
        '```json\n{"action": "load", "skill": "demo"}\n```',
    ])
    service = EvalService(_registry(tmp_path), fake, _eval_file(tmp_path))
    report = asyncio.run(service.run())
    assert report.summary.total == 4
    assert report.summary.passed == 4
    assert report.summary.accuracy == 1.0
    assert report.summary.by_category["normal"] == {"total": 1, "passed": 1}
    assert service.last_report is report
    system_message = fake.chat_calls[0][0]
    assert system_message.role == "system"
    assert "- demo: demo skill" in system_message.content
    # Regression: the rendered prompt must contain a literal JSON object example.
    assert '{"action":' in system_message.content


def test_non_string_action_recorded_as_error(tmp_path):
    # Regression: unhashable action (list/dict) must not escape fault tolerance.
    fake = FakeLLM(chat_replies=[
        '{"action": ["load"]}',
        '{"action": "clarify", "skill": null}',
        '{"action": "none", "skill": null}',
        '{"action": "load", "skill": "demo"}',
    ])
    service = EvalService(_registry(tmp_path), fake, _eval_file(tmp_path))
    report = asyncio.run(service.run())
    assert report.results[0].error is not None
    assert report.results[0].passed is False
    assert report.summary.total == 4
    assert report.summary.passed == 3


def test_single_failure_does_not_abort(tmp_path):
    fake = FakeLLM(chat_replies=[
        LLMError("boom"),
        '{"action": "clarify", "skill": null}',
        "not json at all",
        '{"action": "load", "skill": "demo"}',
    ])
    service = EvalService(_registry(tmp_path), fake, _eval_file(tmp_path))
    report = asyncio.run(service.run())
    assert report.results[0].error is not None
    assert report.results[0].passed is False
    assert report.results[2].error is not None
    assert report.summary.passed == 2
    assert report.summary.total == 4


def test_bad_eval_line_reports_path_and_lineno(tmp_path):
    import pytest

    path = tmp_path / "bad-eval.jsonl"
    good = json.dumps(
        {"id": 1, "query": "q1", "expected_skill": "demo", "category": "normal"}
    )
    path.write_text(good + "\n{not valid json}\n", encoding="utf-8")
    service = EvalService(_registry(tmp_path), FakeLLM(), path)
    with pytest.raises(ValueError) as excinfo:
        asyncio.run(service.run())
    message = str(excinfo.value)
    assert "bad-eval.jsonl" in message
    assert ":2:" in message


def test_empty_eval_file_returns_zero_summary(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    service = EvalService(_registry(tmp_path), FakeLLM(), path)
    report = asyncio.run(service.run())
    assert report.results == []
    assert report.summary.total == 0
    assert report.summary.passed == 0
    assert report.summary.accuracy == 0.0
    assert report.summary.by_category == {}


def test_by_category_aggregates_multiple_rows(tmp_path):
    cases = [
        {"id": 1, "query": "q1", "expected_skill": "demo", "category": "normal"},
        {"id": 2, "query": "q2", "expected_skill": "demo", "category": "normal"},
    ]
    path = tmp_path / "eval.jsonl"
    path.write_text("\n".join(json.dumps(c) for c in cases) + "\n", encoding="utf-8")
    fake = FakeLLM(chat_replies=[
        '{"action": "load", "skill": "demo"}',
        '{"action": "load", "skill": "other"}',
    ])
    service = EvalService(_registry(tmp_path), fake, path)
    report = asyncio.run(service.run())
    assert report.summary.by_category == {"normal": {"total": 2, "passed": 1}}
    assert report.summary.total == 2
    assert report.summary.passed == 1
    assert report.summary.accuracy == 0.5
