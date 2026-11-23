"""API tests for skills, agent chat, debug and eval endpoints."""

import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.llm.base import LLMNotConfiguredError, ToolCall, ToolChatResult
from app.services.skills.agent import AgentService, get_agent_service
from app.services.skills.evals import EvalService, get_eval_service
from app.services.skills.registry import SkillRegistry, get_registry
from fakes import FakeLLM, fake_usage


def _setup(tmp_path):
    skill_dir = tmp_path / "skills" / "demo"
    (skill_dir / "templates").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo skill\n---\n\n# Demo body\n", encoding="utf-8"
    )
    (skill_dir / "templates" / "t.md").write_text("template content", encoding="utf-8")
    broken = tmp_path / "skills" / "broken"
    broken.mkdir()
    (broken / "SKILL.md").write_text("---\nname: broken\n", encoding="utf-8")
    eval_path = tmp_path / "eval.jsonl"
    eval_path.write_text(
        json.dumps({"id": 1, "query": "q1", "expected_skill": "demo", "category": "normal"}) + "\n",
        encoding="utf-8",
    )
    return SkillRegistry(dirs=[tmp_path / "skills"], budget=2000, truncate_chars=80), eval_path


def _app(tmp_path, fake):
    registry, eval_path = _setup(tmp_path)
    # Share one instance per app: overrides are called once per request,
    # so constructing services inside the lambda would lose cross-request state.
    agent = AgentService(registry, fake, 8)
    evals = EvalService(registry, fake, eval_path)
    app = create_app()
    app.dependency_overrides[get_registry] = lambda: registry
    app.dependency_overrides[get_agent_service] = lambda: agent
    app.dependency_overrides[get_eval_service] = lambda: evals
    return TestClient(app)


def test_list_skills_shape(tmp_path):
    client = _app(tmp_path, FakeLLM())
    response = client.get("/api/skills")
    assert response.status_code == 200
    body = response.json()
    assert body["injection"]["strategy"] == "full"
    assert body["injection"]["budget"] == 2000
    demo = next(s for s in body["skills"] if s["name"] == "demo")
    assert demo["source_dir"] == "skills"
    assert demo["status"] == "active"
    assert demo["tokens"] > 0
    assert demo["loaded"] is False
    assert any("broken" in i["path"] for i in body["issues"])


def test_rescan_endpoint(tmp_path):
    client = _app(tmp_path, FakeLLM())
    response = client.post("/api/skills/rescan")
    assert response.status_code == 200
    assert response.json()["skills"]


def test_simulate_toggle_degrades_injection(tmp_path):
    client = _app(tmp_path, FakeLLM())
    response = client.post("/api/debug/simulate", json={"enabled": True})
    assert response.status_code == 200
    body = response.json()
    assert body["injection"]["skill_count"] == 201
    assert body["injection"]["strategy"] == "names_only"
    response = client.post("/api/debug/simulate", json={"enabled": False})
    assert response.json()["injection"]["skill_count"] == 1


def test_agent_chat_returns_events_and_usage(tmp_path):
    fake = FakeLLM(tool_replies=[
        ToolChatResult(
            content=None,
            tool_calls=[ToolCall(id="c1", name="load_skill", arguments='{"name": "demo"}')],
            model="fake", usage=fake_usage(),
        ),
        ToolChatResult(content="done", tool_calls=[], model="fake", usage=fake_usage()),
    ])
    client = _app(tmp_path, fake)
    response = client.post("/api/agent/chat", json={"session_id": "s1", "message": "use demo"})
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "done"
    assert body["events"][0]["type"] == "load_skill"
    assert body["events"][0]["ok"] is True
    assert body["usage"]["input_tokens"] == 200
    assert body["tool_rounds"] == 1
    listed = client.get("/api/skills", params={"session_id": "s1"}).json()
    demo = next(s for s in listed["skills"] if s["name"] == "demo")
    assert demo["loaded"] is True


def test_agent_chat_not_configured_returns_503(tmp_path):
    fake = FakeLLM(tool_replies=[LLMNotConfiguredError("no key")])
    client = _app(tmp_path, fake)
    response = client.post("/api/agent/chat", json={"session_id": "s1", "message": "hi"})
    assert response.status_code == 503


def test_agent_chat_empty_message_returns_422(tmp_path):
    client = _app(tmp_path, FakeLLM())
    response = client.post("/api/agent/chat", json={"session_id": "s1", "message": ""})
    assert response.status_code == 422


def test_evals_run_and_cached_results(tmp_path):
    fake = FakeLLM(chat_replies=['{"action": "load", "skill": "demo"}'])
    client = _app(tmp_path, fake)
    empty = client.get("/api/evals/results").json()
    assert empty["results"] == []
    response = client.post("/api/evals/run")
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["passed"] == 1
    assert body["results"][0]["passed"] is True
    cached = client.get("/api/evals/results").json()
    assert cached["summary"]["total"] == 1
