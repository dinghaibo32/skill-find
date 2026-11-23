"""Build the skill catalog text injected into the system prompt.

Token counts use tiktoken cl100k_base and are estimates for qwen models.
When the text exceeds the budget, degrade: full -> truncated -> names_only.
"""

from functools import lru_cache

import tiktoken

from app.services.skills.models import InjectionResult, SkillRecord


@lru_cache(maxsize=1)
def _get_encoder():
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Estimated token count for a piece of text."""
    return len(_get_encoder().encode(text))


def skill_line(record: SkillRecord) -> str:
    return f"- {record.name}: {record.description}"


def build_injection(
    records: list[SkillRecord], budget: int, truncate_chars: int
) -> InjectionResult:
    """Build injection text; names_only is best-effort and may still exceed the budget."""
    active = [r for r in records if r.status == "active"]
    full_text = "\n".join(skill_line(r) for r in active)
    tokens = count_tokens(full_text)
    if tokens <= budget:
        return InjectionResult(
            text=full_text, tokens=tokens, strategy="full",
            budget=budget, skill_count=len(active),
        )
    truncated_lines = []
    for record in active:
        description = record.description
        if len(description) > truncate_chars:
            description = description[:truncate_chars] + "…"
        truncated_lines.append(f"- {record.name}: {description}")
    truncated_text = "\n".join(truncated_lines)
    tokens = count_tokens(truncated_text)
    if tokens <= budget:
        return InjectionResult(
            text=truncated_text, tokens=tokens, strategy="truncated",
            budget=budget, skill_count=len(active),
        )
    names_text = "\n".join(f"- {r.name}" for r in active)
    return InjectionResult(
        text=names_text, tokens=count_tokens(names_text), strategy="names_only",
        budget=budget, skill_count=len(active),
    )
