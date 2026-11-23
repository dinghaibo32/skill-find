"""Agent loop: inject skill catalog, execute tool calls, record events."""

import json

from pydantic import BaseModel

from app.core.config import get_settings
from app.services.llm import get_llm_client
from app.services.llm.base import ChatMessage, LLMClient, LLMUsage, ToolCall
from app.services.skills.files import SkillFileError, read_skill_file
from app.services.skills.injector import build_injection
from app.services.skills.models import AgentEvent
from app.services.skills.registry import SYNTHETIC_SOURCE, SkillRegistry, get_registry
from app.services.skills.scanner import SkillParseError

LOAD_SKILL_TOOL = {
    "type": "function",
    "function": {
        "name": "load_skill",
        "description": "Load the full markdown body of a skill by name.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
}

READ_SKILL_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_skill_file",
        "description": "Read a companion file referenced inside a skill body.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "path": {"type": "string", "description": "Relative path inside the skill directory."},
            },
            "required": ["name", "path"],
        },
    },
}

SYSTEM_PROMPT_TEMPLATE = (
    "You are a helpful assistant with access to a skill library.\n"
    "Available skills (name: description):\n{skills}\n\n"
    "When a user request matches a skill, call load_skill(name) to get its full "
    "instructions before answering. Files referenced inside a skill body can be "
    "read with read_skill_file(name, path). If no skill matches, answer directly. "
    "If the request is ambiguous between skills, ask a clarifying question."
)


class AgentTurnResult(BaseModel):
    reply: str
    events: list[AgentEvent]
    usage: LLMUsage
    injection_tokens: int
    tool_rounds: int


class AgentService:
    """In-memory sessions; system prompt is rebuilt each turn (hot reload)."""

    def __init__(self, registry: SkillRegistry, client: LLMClient, max_tool_rounds: int = 8) -> None:
        self._registry = registry
        self._client = client
        self._max_tool_rounds = max_tool_rounds
        self._sessions: dict[str, list[ChatMessage]] = {}
        self._loaded: dict[str, set[str]] = {}

    def loaded_skills(self, session_id: str) -> set[str]:
        return set(self._loaded.get(session_id, ()))

    async def run_turn(self, session_id: str, user_message: str) -> AgentTurnResult:
        self._registry.refresh()
        injection = build_injection(
            self._registry.records, self._registry.budget, self._registry.truncate_chars
        )
        history = self._sessions.setdefault(session_id, [])
        messages = [
            ChatMessage(role="system", content=SYSTEM_PROMPT_TEMPLATE.format(skills=injection.text)),
            *history,
            ChatMessage(role="user", content=user_message),
        ]
        events: list[AgentEvent] = []
        input_tokens = output_tokens = total_tokens = 0
        cost = 0.0
        rounds = 0

        def accumulate(usage: LLMUsage) -> None:
            nonlocal input_tokens, output_tokens, total_tokens, cost
            input_tokens += usage.input_tokens
            output_tokens += usage.output_tokens
            total_tokens += usage.total_tokens
            cost += usage.cost

        while True:
            result = await self._client.chat_with_tools(
                messages, [LOAD_SKILL_TOOL, READ_SKILL_FILE_TOOL]
            )
            accumulate(result.usage)
            if not result.tool_calls:
                reply = result.content or ""
                messages.append(ChatMessage(role="assistant", content=reply))
                break
            rounds += 1
            messages.append(
                ChatMessage(role="assistant", content=result.content or "", tool_calls=result.tool_calls)
            )
            for call in result.tool_calls:
                output, event = self._execute_tool(call)
                if event is not None:
                    events.append(event)
                    if event.type == "load_skill" and event.ok:
                        self._loaded.setdefault(session_id, set()).add(event.skill)
                messages.append(ChatMessage(role="tool", content=output, tool_call_id=call.id))
            if rounds >= self._max_tool_rounds:
                final = await self._client.chat(messages)
                accumulate(final.usage)
                reply = final.content
                messages.append(ChatMessage(role="assistant", content=reply))
                break

        history.extend(messages[1 + len(history):])
        return AgentTurnResult(
            reply=reply,
            events=events,
            usage=LLMUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost=round(cost, 6),
            ),
            injection_tokens=injection.tokens,
            tool_rounds=rounds,
        )

    def _execute_tool(self, call: ToolCall) -> tuple[str, AgentEvent | None]:
        try:
            args = json.loads(call.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        name = str(args.get("name", ""))
        if call.name == "load_skill":
            record = self._registry.get_active(name)
            if record is None:
                return self._tool_error("load_skill", name, None, f"unknown skill: {name}")
            try:
                body = self._registry.load_body(record)
            except (SkillParseError, OSError, UnicodeDecodeError) as exc:
                return self._tool_error("load_skill", name, None, str(exc))
            return body, AgentEvent(type="load_skill", skill=name, ok=True)
        if call.name == "read_skill_file":
            path = str(args.get("path", ""))
            record = self._registry.get_active(name)
            if record is None:
                return self._tool_error("read_skill_file", name, path, f"unknown skill: {name}")
            if record.source_dir == SYNTHETIC_SOURCE:
                return self._tool_error("read_skill_file", name, path, "synthetic skills have no files")
            try:
                content = read_skill_file(record, path)
            except (SkillFileError, OSError, UnicodeDecodeError) as exc:
                return self._tool_error("read_skill_file", name, path, str(exc))
            return content, AgentEvent(type="read_skill_file", skill=name, path=path, ok=True)
        return f"Error: unknown tool {call.name}", None

    @staticmethod
    def _tool_error(
        tool_type: str, name: str, path: str | None, reason: str
    ) -> tuple[str, AgentEvent]:
        return f"Error: {reason}", AgentEvent(
            type=tool_type, skill=name, path=path, ok=False, error=reason
        )


_agent_service: AgentService | None = None


def get_agent_service() -> AgentService:
    """Process-wide singleton, used as a FastAPI dependency."""
    global _agent_service
    if _agent_service is None:
        settings = get_settings()
        _agent_service = AgentService(
            get_registry(), get_llm_client(), settings.agent_max_tool_rounds
        )
    return _agent_service
