"""Tests for the agent loop using a scripted fake LLM."""

import asyncio
import os

from app.services.llm.base import ToolCall, ToolChatResult
from app.services.skills.agent import AgentService
from app.services.skills.registry import SkillRegistry
from fakes import FakeLLM, fake_usage


def _registry(tmp_path) -> SkillRegistry:
    skill_dir = tmp_path / "skills" / "demo"
    (skill_dir / "templates").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo skill\n---\n\n"
        "# Demo body\nRead templates/t.md for the template.\n",
        encoding="utf-8",
    )
    (skill_dir / "templates" / "t.md").write_text("template content", encoding="utf-8")
    return SkillRegistry(dirs=[tmp_path / "skills"], budget=2000, truncate_chars=80)


def _tool_turn(calls):
    return ToolChatResult(content=None, tool_calls=calls, model="fake", usage=fake_usage())


def _final(text):
    return ToolChatResult(content=text, tool_calls=[], model="fake", usage=fake_usage())


def test_turn_without_tools(tmp_path):
    fake = FakeLLM(tool_replies=[_final("direct answer")])
    service = AgentService(_registry(tmp_path), fake, max_tool_rounds=8)
    result = asyncio.run(service.run_turn("s1", "hello"))
    assert result.reply == "direct answer"
    assert result.events == []
    assert result.tool_rounds == 0
    assert result.usage.input_tokens == 100
    assert result.injection_tokens > 0


def test_turn_loads_skill_and_reads_file(tmp_path):
    fake = FakeLLM(tool_replies=[
        _tool_turn([ToolCall(id="c1", name="load_skill", arguments='{"name": "demo"}')]),
        _tool_turn([ToolCall(id="c2", name="read_skill_file",
                             arguments='{"name": "demo", "path": "templates/t.md"}')]),
        _final("final answer"),
    ])
    service = AgentService(_registry(tmp_path), fake, max_tool_rounds=8)
    result = asyncio.run(service.run_turn("s1", "use the demo skill"))
    assert result.reply == "final answer"
    assert result.tool_rounds == 2
    assert [e.type for e in result.events] == ["load_skill", "read_skill_file"]
    assert all(e.ok for e in result.events)
    assert result.events[1].path == "templates/t.md"
    assert result.usage.input_tokens == 300
    assert result.usage.cost == round(0.00018 * 3, 6)
    assert service.loaded_skills("s1") == {"demo"}
    # Snapshots must be independent copies, not references to the live list.
    assert fake.tool_calls_received[0] is not fake.tool_calls_received[-1]
    assert len(fake.tool_calls_received[0]) < len(fake.tool_calls_received[-1])
    last_messages = fake.tool_calls_received[2]
    tool_messages = [m for m in last_messages if m.role == "tool"]
    assert "Demo body" in tool_messages[0].content
    assert tool_messages[1].content == "template content"


def test_traversal_error_returned_as_tool_result(tmp_path):
    fake = FakeLLM(tool_replies=[
        _tool_turn([ToolCall(id="c1", name="read_skill_file",
                             arguments='{"name": "demo", "path": "../secret.txt"}')]),
        _final("handled"),
    ])
    service = AgentService(_registry(tmp_path), fake, max_tool_rounds=8)
    result = asyncio.run(service.run_turn("s1", "read outside"))
    assert result.reply == "handled"
    assert result.events[0].ok is False
    assert "escapes" in result.events[0].error
    tool_message = [m for m in fake.tool_calls_received[1] if m.role == "tool"][0]
    assert tool_message.content.startswith("Error:")


def test_unknown_skill_error(tmp_path):
    fake = FakeLLM(tool_replies=[
        _tool_turn([ToolCall(id="c1", name="load_skill", arguments='{"name": "nope"}')]),
        _final("ok"),
    ])
    service = AgentService(_registry(tmp_path), fake, max_tool_rounds=8)
    result = asyncio.run(service.run_turn("s1", "load nope"))
    assert result.events[0].ok is False
    assert "unknown skill" in result.events[0].error


def test_round_limit_forces_final_answer(tmp_path):
    fake = FakeLLM(
        tool_replies=[
            _tool_turn([ToolCall(id="c1", name="load_skill", arguments='{"name": "demo"}')])
        ],
        chat_replies=["forced final"],
    )
    service = AgentService(_registry(tmp_path), fake, max_tool_rounds=1)
    result = asyncio.run(service.run_turn("s1", "loop"))
    assert result.reply == "forced final"
    assert result.tool_rounds == 1
    assert len(fake.chat_calls) == 1
    # The forced final reply must be persisted into the session history.
    second = asyncio.run(service.run_turn("s1", "next turn"))
    assert second.tool_rounds == 0
    second_turn_messages = fake.tool_calls_received[1]
    assert "forced final" in [m.content for m in second_turn_messages]


def test_load_skill_invalid_utf8_body_returns_error_event(tmp_path):
    registry = _registry(tmp_path)
    skill_file = tmp_path / "skills" / "demo" / "SKILL.md"
    original = skill_file.stat()
    # Corrupt the body bytes after registration; restore mtime so refresh()
    # sees no change and the registered record stays active.
    skill_file.write_bytes(b"---\nname: demo\ndescription: demo skill\n---\n\n\xff\xfe bad bytes")
    os.utime(skill_file, (original.st_atime, original.st_mtime))
    fake = FakeLLM(tool_replies=[
        _tool_turn([ToolCall(id="c1", name="load_skill", arguments='{"name": "demo"}')]),
        _final("recovered"),
    ])
    service = AgentService(registry, fake, max_tool_rounds=8)
    result = asyncio.run(service.run_turn("s1", "load demo"))
    assert result.reply == "recovered"
    assert result.events[0].ok is False
    assert "utf-8" in result.events[0].error
    tool_message = [m for m in fake.tool_calls_received[1] if m.role == "tool"][0]
    assert tool_message.content.startswith("Error:")


def test_loaded_skills_returns_copy(tmp_path):
    fake = FakeLLM(tool_replies=[
        _tool_turn([ToolCall(id="c1", name="load_skill", arguments='{"name": "demo"}')]),
        _final("done"),
    ])
    service = AgentService(_registry(tmp_path), fake, max_tool_rounds=8)
    asyncio.run(service.run_turn("s1", "load demo"))
    loaded = service.loaded_skills("s1")
    loaded.clear()
    assert service.loaded_skills("s1") == {"demo"}


def test_history_kept_across_turns(tmp_path):
    fake = FakeLLM(tool_replies=[_final("first"), _final("second")])
    service = AgentService(_registry(tmp_path), fake, max_tool_rounds=8)
    asyncio.run(service.run_turn("s1", "turn one"))
    asyncio.run(service.run_turn("s1", "turn two"))
    second_call = fake.tool_calls_received[1]
    contents = [m.content for m in second_call]
    assert "turn one" in contents
    assert "first" in contents
    assert "turn two" in contents
    assert second_call[0].role == "system"
