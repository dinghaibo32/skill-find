"""Routing eval: inject name+description only, score the model's choice."""

import json
from pathlib import Path

from pydantic import BaseModel

from app.core.config import get_repo_root
from app.services.llm import get_llm_client
from app.services.llm.base import ChatMessage, LLMClient, LLMError
from app.services.skills.injector import build_injection
from app.services.skills.registry import SkillRegistry, get_registry

EVAL_SYSTEM_TEMPLATE = (
    "You are a skill router. Available skills (name: description):\n{skills}\n\n"
    "Decide how to handle the user request. Reply with ONLY a JSON object: "
    '{{"action": "load"|"clarify"|"none", "skill": "<skill name or null>"}}. '
    "Use load when exactly one skill clearly matches, clarify when the request "
    "is ambiguous between skills, none when no skill applies."
)


class EvalCase(BaseModel):
    id: int
    query: str
    expected_skill: str | None
    category: str
    reason: str = ""


class EvalActual(BaseModel):
    action: str
    skill: str | None = None


class EvalRowResult(BaseModel):
    id: int
    query: str
    category: str
    expected_skill: str | None
    actual: EvalActual | None
    passed: bool
    error: str | None = None


class EvalSummary(BaseModel):
    total: int
    passed: int
    accuracy: float
    by_category: dict[str, dict[str, int]]


class EvalReport(BaseModel):
    results: list[EvalRowResult]
    summary: EvalSummary


def parse_actual(content: str) -> EvalActual:
    """Extract the first JSON object from a reply (tolerates code fences).

    Decoding starts at the first '{' and stops at the end of that object,
    so trailing text or extra JSON objects are ignored. Raises ValueError
    when no object starts there or the action is not allowed.
    """
    start = content.find("{")
    if start == -1:
        raise ValueError(f"no JSON object in reply: {content!r}")
    data, _ = json.JSONDecoder().raw_decode(content[start:])
    action = data.get("action")
    if action not in ("load", "clarify", "none"):
        raise ValueError(f"invalid action: {action!r}")
    return EvalActual(action=action, skill=data.get("skill"))


def score(category: str, expected_skill: str | None, actual: EvalActual) -> bool:
    if category == "ambiguous":
        return actual.action == "clarify"
    if expected_skill is None:
        return actual.action == "none"
    return actual.action == "load" and actual.skill == expected_skill


class EvalService:
    def __init__(self, registry: SkillRegistry, client: LLMClient, eval_path: Path) -> None:
        self._registry = registry
        self._client = client
        self._eval_path = eval_path
        self.last_report: EvalReport | None = None

    async def run(self) -> EvalReport:
        self._registry.refresh()
        injection = build_injection(
            self._registry.records, self._registry.budget, self._registry.truncate_chars
        )
        system = ChatMessage(
            role="system", content=EVAL_SYSTEM_TEMPLATE.format(skills=injection.text)
        )
        lines = self._eval_path.read_text(encoding="utf-8").splitlines()
        # Eval files are curated repo data: bad lines fail fast, with location.
        cases: list[EvalCase] = []
        for lineno, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                cases.append(EvalCase.model_validate_json(line))
            except ValueError as exc:
                raise ValueError(f"{self._eval_path}:{lineno}: {exc}") from exc
        rows: list[EvalRowResult] = []
        for case in cases:
            try:
                result = await self._client.chat(
                    [system, ChatMessage(role="user", content=case.query)]
                )
                actual = parse_actual(result.content)
                rows.append(EvalRowResult(
                    id=case.id, query=case.query, category=case.category,
                    expected_skill=case.expected_skill, actual=actual,
                    passed=score(case.category, case.expected_skill, actual),
                ))
            except (LLMError, ValueError) as exc:
                rows.append(EvalRowResult(
                    id=case.id, query=case.query, category=case.category,
                    expected_skill=case.expected_skill, actual=None,
                    passed=False, error=str(exc),
                ))
        by_category: dict[str, dict[str, int]] = {}
        for row in rows:
            bucket = by_category.setdefault(row.category, {"total": 0, "passed": 0})
            bucket["total"] += 1
            if row.passed:
                bucket["passed"] += 1
        passed = sum(1 for r in rows if r.passed)
        report = EvalReport(
            results=rows,
            summary=EvalSummary(
                total=len(rows),
                passed=passed,
                accuracy=round(passed / len(rows), 4) if rows else 0.0,
                by_category=by_category,
            ),
        )
        self.last_report = report
        return report


_eval_service: EvalService | None = None


def get_eval_service() -> EvalService:
    """Process-wide singleton, used as a FastAPI dependency."""
    global _eval_service
    if _eval_service is None:
        _eval_service = EvalService(
            get_registry(), get_llm_client(),
            get_repo_root() / "evals" / "routing-eval.jsonl",
        )
    return _eval_service
