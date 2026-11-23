# Skill 系统与演示页面实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Skill 发现/冲突裁决/注入/按需加载/热更新系统，扩展 LLM tool-calling，并交付左右双栏演示页面（skill 列表、对话、评测表、调试面板）。

**Architecture:** 后端新增 `app/services/skills/` 分层模块（scanner/registry/injector/files/agent/evals），复用并扩展现有 LLMClient 协议；前端 Vue3 按 api/types/components 分层新增组件。规格见 `docs/superpowers/specs/2026-11-23-skill-system-design.md`。

**Tech Stack:** FastAPI + pydantic + openai SDK + tiktoken + pyyaml；Vue3 + TS + Vite；pytest。

**工程规则（每个任务都必须遵守）：**
- 代码、注释、标识符、API 字段、状态名一律英文；commit message 用中文。
- 测试命令：在 `backend` 目录执行 `.venv\Scripts\python.exe -m pytest -q`（下文简写为 `pytest`）。
- 新建文件后必须校验末尾换行（PowerShell）：`[System.IO.File]::ReadAllBytes($p)[-1]` 应为 `10`；若不是，`[System.IO.File]::AppendAllText($p, "`n")` 修复后再提交。
- 依赖变更后必须在 backend 目录 `uv lock` 并 `uv lock --check`。
- 当前分支 `feature/skill-system`，所有提交都在此分支。

---

### Task 1: 依赖、配置与样例素材入库

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_config.py`
- Commit fixtures: `skills/`、`skills-extra/`、`evals/`（已存在于工作区，未入库）

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_config.py` 末尾追加：

```python
def test_skill_settings_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.skill_dirs == ["skills", "skills-extra"]
    assert settings.skill_injection_token_budget == 2000
    assert settings.skill_desc_truncate_chars == 80
    assert settings.agent_max_tool_rounds == 8


def test_repo_root_points_to_workspace() -> None:
    from app.core.config import get_repo_root

    assert (get_repo_root() / "skills").is_dir()
    assert (get_repo_root() / "evals" / "routing-eval.jsonl").is_file()
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_config.py -q`
Expected: FAIL（`AttributeError: ... skill_dirs` / `ImportError: get_repo_root`）

- [ ] **Step 3: 实现配置**

`backend/pyproject.toml` 的 `dependencies` 追加两行（放在 `"openai>=1.40",` 之后）：

```toml
    "pyyaml>=6.0",
    "tiktoken>=0.7",
```

`backend/app/core/config.py`：顶部 import 区加 `from pathlib import Path`；`Settings` 类末尾（`llm_output_price_per_million` 之后）追加：

```python
    # --- Skill system settings ---
    # Directories scanned for skills, relative to the repo root.
    # Earlier entries win name conflicts.
    skill_dirs: list[str] = ["skills", "skills-extra"]
    skill_injection_token_budget: int = 2000
    skill_desc_truncate_chars: int = 80
    agent_max_tool_rounds: int = 8
```

文件末尾追加：

```python
def get_repo_root() -> Path:
    """Repo root resolved from this file: backend/app/core/config.py."""
    return Path(__file__).resolve().parents[3]
```

`backend/.env.example` 末尾追加：

```dotenv
# --- Skill system ---
SKILL_DIRS=["skills","skills-extra"]
SKILL_INJECTION_TOKEN_BUDGET=2000
SKILL_DESC_TRUNCATE_CHARS=80
AGENT_MAX_TOOL_ROUNDS=8
```

- [ ] **Step 4: 安装依赖并同步锁文件**

在 `backend` 目录依次执行：

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]"
uv lock
uv lock --check
```

Expected: 安装成功；`uv lock --check` 输出 `Resolved ...` 且退出码 0。
注意：tiktoken 首次使用时会联网下载 cl100k_base 词表并缓存，之后离线可用。

- [ ] **Step 5: 运行确认通过**

Run: `pytest -q`
Expected: 全部 PASS（原有 22 项 + 新增 2 项）

- [ ] **Step 6: 提交（含样例素材）**

```powershell
git add backend/pyproject.toml backend/uv.lock backend/app/core/config.py backend/.env.example backend/tests/test_config.py skills skills-extra evals
git commit -m "feat: Skill 系统配置与依赖，入库 skill 样例与路由评测集"
```

---

### Task 2: Skill 模型与扫描器（frontmatter 解析/容错/冲突裁决）

**Files:**
- Create: `backend/app/services/skills/__init__.py`
- Create: `backend/app/services/skills/models.py`
- Create: `backend/app/services/skills/scanner.py`
- Test: `backend/tests/test_skill_scanner.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_skill_scanner.py`：

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_skill_scanner.py -q`
Expected: FAIL（`ModuleNotFoundError: app.services.skills`）

- [ ] **Step 3: 实现模型与扫描器**

创建 `backend/app/services/skills/__init__.py`：

```python
"""Skill system: discovery, injection, lazy loading, hot reload."""
```

创建 `backend/app/services/skills/models.py`：

```python
"""Data models shared across the skill system."""

from typing import Literal

from pydantic import BaseModel


class SkillRecord(BaseModel):
    """One scanned skill. Overridden records keep their own source path."""

    name: str
    description: str
    source_dir: str
    skill_path: str
    status: Literal["active", "overridden"] = "active"
    overridden_by: str | None = None
    mtime: float = 0.0


class ScanIssue(BaseModel):
    """A skipped candidate with a human-readable reason."""

    path: str
    reason: str


class ScanResult(BaseModel):
    skills: list[SkillRecord]
    issues: list[ScanIssue]


class InjectionResult(BaseModel):
    """System-prompt injection text with token accounting."""

    text: str
    tokens: int
    strategy: Literal["full", "truncated", "names_only"]
    budget: int
    skill_count: int


class AgentEvent(BaseModel):
    """One tool execution inside an agent turn."""

    type: Literal["load_skill", "read_skill_file"]
    skill: str
    path: str | None = None
    ok: bool
    error: str | None = None
```

创建 `backend/app/services/skills/scanner.py`：

```python
"""Directory scanning with frontmatter parsing and conflict resolution."""

from pathlib import Path

import yaml

from app.services.skills.models import ScanIssue, ScanResult, SkillRecord


class SkillParseError(ValueError):
    """Raised when a SKILL.md frontmatter is invalid."""


def parse_skill_file(path: Path) -> tuple[str, str, str]:
    """Return (name, description, body). Raise SkillParseError when invalid."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillParseError("missing opening '---' frontmatter delimiter")
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        raise SkillParseError("missing closing '---' frontmatter delimiter")
    try:
        meta = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as exc:
        raise SkillParseError(f"invalid YAML frontmatter: {exc}") from exc
    if not isinstance(meta, dict):
        raise SkillParseError("frontmatter is not a mapping")
    name = meta.get("name")
    description = meta.get("description")
    if not isinstance(name, str) or not name.strip():
        raise SkillParseError("frontmatter field 'name' must be a non-empty string")
    if not isinstance(description, str) or not description.strip():
        raise SkillParseError("frontmatter field 'description' must be a non-empty string")
    body = "\n".join(lines[end + 1 :]).strip()
    return name.strip(), description.strip(), body


def scan_directories(dirs: list[Path]) -> ScanResult:
    """Scan dirs in priority order; first registration wins name conflicts.

    A broken candidate is skipped with a ScanIssue and never aborts the scan.
    """
    skills: list[SkillRecord] = []
    issues: list[ScanIssue] = []
    winners: dict[str, SkillRecord] = {}
    for directory in dirs:
        if not directory.is_dir():
            issues.append(ScanIssue(path=str(directory), reason="skill directory does not exist"))
            continue
        for child in sorted(directory.iterdir()):
            if not child.is_dir():
                continue
            skill_file = child / "SKILL.md"
            if not skill_file.is_file():
                issues.append(ScanIssue(path=str(child), reason="SKILL.md not found"))
                continue
            try:
                name, description, _ = parse_skill_file(skill_file)
            except (SkillParseError, OSError, UnicodeDecodeError) as exc:
                issues.append(ScanIssue(path=str(skill_file), reason=str(exc)))
                continue
            record = SkillRecord(
                name=name,
                description=description,
                source_dir=directory.name,
                skill_path=str(skill_file),
                mtime=skill_file.stat().st_mtime,
            )
            if name in winners:
                record.status = "overridden"
                record.overridden_by = winners[name].source_dir
            else:
                winners[name] = record
            skills.append(record)
    return ScanResult(skills=skills, issues=issues)
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_skill_scanner.py -q`
Expected: 9 passed

- [ ] **Step 5: 校验新文件末尾换行并提交**

对 3 个新文件逐一校验末字节为 10（见工程规则），然后：

```powershell
git add backend/app/services/skills backend/tests/test_skill_scanner.py
git commit -m "feat: Skill 扫描器支持 frontmatter 容错与目录优先级冲突裁决"
```

---

### Task 3: 注入器（tiktoken 计数 + 预算三档降级）

**Files:**
- Create: `backend/app/services/skills/injector.py`
- Test: `backend/tests/test_skill_injector.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_skill_injector.py`：

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_skill_injector.py -q`
Expected: FAIL（`ModuleNotFoundError: ... injector`）

- [ ] **Step 3: 实现注入器**

创建 `backend/app/services/skills/injector.py`：

```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_skill_injector.py -q`
Expected: 5 passed（首次运行 tiktoken 需联网下载词表，属正常）

- [ ] **Step 5: 校验末尾换行并提交**

```powershell
git add backend/app/services/skills/injector.py backend/tests/test_skill_injector.py
git commit -m "feat: Skill 注入器支持 tiktoken 计数与预算三档降级"
```

---

### Task 4: 安全文件读取（防路径穿越）

**Files:**
- Create: `backend/app/services/skills/files.py`
- Test: `backend/tests/test_skill_files.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_skill_files.py`：

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_skill_files.py -q`
Expected: FAIL（`ModuleNotFoundError: ... files`）

- [ ] **Step 3: 实现安全读取**

创建 `backend/app/services/skills/files.py`：

```python
"""Read skill companion files without escaping the skill directory."""

from pathlib import Path

from app.services.skills.models import SkillRecord

MAX_FILE_BYTES = 50 * 1024


class SkillFileError(Exception):
    """Raised when a companion file cannot be safely read."""


def read_skill_file(record: SkillRecord, path: str) -> str:
    """Resolve path inside the skill root; reject traversal and oversized files."""
    if Path(path).is_absolute():
        raise SkillFileError("absolute paths are not allowed")
    root = Path(record.skill_path).parent.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise SkillFileError("path escapes the skill directory")
    if not target.is_file():
        raise SkillFileError(f"file not found: {path}")
    if target.stat().st_size > MAX_FILE_BYTES:
        raise SkillFileError("file exceeds 50KB limit")
    return target.read_text(encoding="utf-8")
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_skill_files.py -q`
Expected: 6 passed

- [ ] **Step 5: 校验末尾换行并提交**

```powershell
git add backend/app/services/skills/files.py backend/tests/test_skill_files.py
git commit -m "feat: Skill 附带文件安全读取，拒绝路径穿越与超限文件"
```

---

### Task 5: 注册表（mtime 热更新 + 200 合成 skill overlay）

**Files:**
- Create: `backend/app/services/skills/registry.py`
- Test: `backend/tests/test_skill_registry.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_skill_registry.py`：

```python
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
    skills_dir.mkdir()
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
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_skill_registry.py -q`
Expected: FAIL（`ModuleNotFoundError: ... registry`）

- [ ] **Step 3: 实现注册表**

创建 `backend/app/services/skills/registry.py`：

```python
"""Skill registry: mtime-based hot reload plus a synthetic overlay.

refresh() is cheap (stat calls only) and runs before every agent turn,
so file edits take effect on the next turn without a restart.
"""

from pathlib import Path

from app.core.config import get_repo_root, get_settings
from app.services.skills.models import ScanIssue, ScanResult, SkillRecord
from app.services.skills.scanner import parse_skill_file, scan_directories

SYNTHETIC_SOURCE = "synthetic"


def synthetic_skills(count: int = 200) -> list[SkillRecord]:
    """Deterministic in-memory skills used to demo injection length control."""
    return [
        SkillRecord(
            name=f"demo-skill-{i:03d}",
            description=(
                f"Simulated skill #{i}: handles demo task type {i}, "
                "used to showcase injection length control with many skills."
            ),
            source_dir=SYNTHETIC_SOURCE,
            skill_path=f"<synthetic>/demo-skill-{i:03d}/SKILL.md",
        )
        for i in range(1, count + 1)
    ]


class SkillRegistry:
    def __init__(self, dirs: list[Path], budget: int, truncate_chars: int) -> None:
        self._dirs = dirs
        self.budget = budget
        self.truncate_chars = truncate_chars
        self._scan = ScanResult(skills=[], issues=[])
        self._snapshot: dict[str, float] = {}
        self._simulate = False
        self.force_rescan()

    @property
    def records(self) -> list[SkillRecord]:
        if self._simulate:
            return self._scan.skills + synthetic_skills()
        return self._scan.skills

    @property
    def issues(self) -> list[ScanIssue]:
        return self._scan.issues

    def get_active(self, name: str) -> SkillRecord | None:
        for record in self.records:
            if record.name == name and record.status == "active":
                return record
        return None

    def load_body(self, record: SkillRecord) -> str:
        if record.source_dir == SYNTHETIC_SOURCE:
            return (
                f"# {record.name}\n\n"
                "This is a simulated skill body for injection-length demos."
            )
        _, _, body = parse_skill_file(Path(record.skill_path))
        return body

    def set_simulate(self, enabled: bool) -> None:
        self._simulate = enabled

    def refresh(self) -> None:
        """Rescan only when the SKILL.md mtime snapshot changed."""
        snapshot = self._current_snapshot()
        if snapshot != self._snapshot:
            self._scan = scan_directories(self._dirs)
            self._snapshot = snapshot

    def force_rescan(self) -> None:
        self._scan = scan_directories(self._dirs)
        self._snapshot = self._current_snapshot()

    def _current_snapshot(self) -> dict[str, float]:
        snapshot: dict[str, float] = {}
        for directory in self._dirs:
            if not directory.is_dir():
                continue
            for child in sorted(directory.iterdir()):
                skill_file = child / "SKILL.md"
                if skill_file.is_file():
                    snapshot[str(skill_file)] = skill_file.stat().st_mtime
        return snapshot


_registry: SkillRegistry | None = None


def get_registry() -> SkillRegistry:
    """Process-wide singleton, used as a FastAPI dependency."""
    global _registry
    if _registry is None:
        settings = get_settings()
        root = get_repo_root()
        _registry = SkillRegistry(
            dirs=[root / d for d in settings.skill_dirs],
            budget=settings.skill_injection_token_budget,
            truncate_chars=settings.skill_desc_truncate_chars,
        )
    return _registry
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_skill_registry.py -q`
Expected: 6 passed

- [ ] **Step 5: 校验末尾换行并提交**

```powershell
git add backend/app/services/skills/registry.py backend/tests/test_skill_registry.py
git commit -m "feat: Skill 注册表支持 mtime 热更新与 200 合成 skill 开关"
```---

### Task 6: LLM 封装扩展 tool calling

**Files:**
- Modify: `backend/app/services/llm/base.py`
- Modify: `backend/app/services/llm/openai_compatible.py`
- Modify: `backend/app/services/llm/__init__.py`
- Modify: `backend/app/schemas/llm.py`（公开接口仍限制 role，保持 422 行为）
- Modify: `backend/app/api/routes/llm.py`（请求模型转换）
- Test: `backend/tests/test_llm_tools.py`

**兼容性要点：** 现有 `test_chat_invalid_role_returns_422` 断言 `/api/llm/chat` 拒绝 `role=tool`。因此内部 `ChatMessage` 扩展 role，但公开请求改用新的 `PublicChatMessage`（仅 system/user/assistant）。现有 `test_chat_returns_content_and_usage` 断言 payload 为 `{"role","content"}` 两键，因此序列化用 `_to_payload` 只输出非空字段。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_llm_tools.py`：

```python
"""Tests for chat_with_tools on the openai-SDK client (no real network)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import APIConnectionError
import httpx

from app.services.llm import openai_compatible
from app.services.llm.base import ChatMessage, LLMError, LLMNotConfiguredError, ToolCall
from app.services.llm.openai_compatible import OpenAICompatibleClient


def _tool_call(id="call_1", name="load_skill", arguments='{"name": "demo"}'):
    return SimpleNamespace(id=id, function=SimpleNamespace(name=name, arguments=arguments))


def _response(content=None, tool_calls=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))],
        usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150),
    )


def _patch_sdk(monkeypatch, response=None, error=None):
    fake = MagicMock()
    if error is not None:
        fake.chat.completions.create = AsyncMock(side_effect=error)
    else:
        fake.chat.completions.create = AsyncMock(return_value=response)
    fake.close = AsyncMock()
    monkeypatch.setattr(openai_compatible, "AsyncOpenAI", MagicMock(return_value=fake))
    return fake


def _client(api_key="sk-test"):
    return OpenAICompatibleClient(
        api_key=api_key,
        base_url="https://example.com/v1",
        model="qwen-plus",
        input_price_per_million=0.8,
        output_price_per_million=2.0,
    )


_TOOLS = [{"type": "function", "function": {"name": "load_skill", "parameters": {}}}]


def _run(client, messages):
    return asyncio.run(client.chat_with_tools(messages, _TOOLS))


def test_returns_tool_calls_and_usage(monkeypatch):
    fake = _patch_sdk(monkeypatch, response=_response(tool_calls=[_tool_call()]))
    result = _run(_client(), [ChatMessage(role="user", content="hi")])
    assert result.content is None
    assert result.tool_calls == [ToolCall(id="call_1", name="load_skill", arguments='{"name": "demo"}')]
    assert result.usage.input_tokens == 100
    assert result.usage.cost == 0.00018
    fake.close.assert_awaited_once()
    kwargs = fake.chat.completions.create.await_args.kwargs
    assert kwargs["tools"] == _TOOLS


def test_plain_reply_has_empty_tool_calls(monkeypatch):
    _patch_sdk(monkeypatch, response=_response(content="done"))
    result = _run(_client(), [ChatMessage(role="user", content="hi")])
    assert result.content == "done"
    assert result.tool_calls == []


def test_tool_message_payload_shape(monkeypatch):
    fake = _patch_sdk(monkeypatch, response=_response(content="final"))
    messages = [
        ChatMessage(role="user", content="hi"),
        ChatMessage(
            role="assistant", content="",
            tool_calls=[ToolCall(id="call_1", name="load_skill", arguments='{"name": "demo"}')],
        ),
        ChatMessage(role="tool", content="body text", tool_call_id="call_1"),
    ]
    _run(_client(), messages)
    payload = fake.chat.completions.create.await_args.kwargs["messages"]
    assert payload[0] == {"role": "user", "content": "hi"}
    assert payload[1] == {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": "call_1", "type": "function",
             "function": {"name": "load_skill", "arguments": '{"name": "demo"}'}}
        ],
    }
    assert payload[2] == {"role": "tool", "content": "body text", "tool_call_id": "call_1"}


def test_plain_chat_payload_unchanged(monkeypatch):
    fake = _patch_sdk(monkeypatch, response=_response(content="hello"))
    asyncio.run(_client().chat([ChatMessage(role="user", content="hello")]))
    payload = fake.chat.completions.create.await_args.kwargs["messages"]
    assert payload == [{"role": "user", "content": "hello"}]


def test_missing_key_raises():
    with pytest.raises(LLMNotConfiguredError):
        _run(_client(api_key=""), [ChatMessage(role="user", content="hi")])


def test_api_error_mapped(monkeypatch):
    error = APIConnectionError(request=httpx.Request("POST", "https://example.com/v1"))
    fake = _patch_sdk(monkeypatch, error=error)
    with pytest.raises(LLMError):
        _run(_client(), [ChatMessage(role="user", content="hi")])
    fake.close.assert_awaited_once()


def test_missing_usage_raises(monkeypatch):
    response = _response(content="done")
    response.usage = None
    _patch_sdk(monkeypatch, response=response)
    with pytest.raises(LLMError):
        _run(_client(), [ChatMessage(role="user", content="hi")])
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_llm_tools.py -q`
Expected: FAIL（`ImportError: cannot import name 'ToolCall'`）

- [ ] **Step 3: 扩展 base.py**

`backend/app/services/llm/base.py`：在 `ChatMessage` 之前新增 `ToolCall`，将 `ChatMessage` 替换为下面的版本；`ToolChatResult` 必须放在 `LLMUsage` 定义之后（它引用 LLMUsage，提前会 NameError）：

```python
class ToolCall(BaseModel):
    """A function call requested by the model. arguments is a raw JSON string."""

    id: str
    name: str
    arguments: str


class ChatMessage(BaseModel):
    """A single chat turn sent to the model, including tool exchanges."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] | None = None


class ToolChatResult(BaseModel):
    """Reply or tool calls, plus per-call usage statistics."""

    content: str | None
    tool_calls: list[ToolCall]
    model: str
    usage: LLMUsage
```

`LLMClient` Protocol 追加方法：

```python
    async def chat_with_tools(
        self, messages: list[ChatMessage], tools: list[dict]
    ) -> ToolChatResult:
        """Send messages with tool definitions; return reply or tool calls."""
        ...
```

- [ ] **Step 4: 扩展 openai_compatible.py**

import 区补充 `ToolCall, ToolChatResult`。类内新增两个辅助方法（放在 `chat` 之前）：

```python
    @staticmethod
    def _to_payload(message: ChatMessage) -> dict:
        data: dict = {"role": message.role, "content": message.content}
        if message.tool_call_id is not None:
            data["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            data["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in message.tool_calls
            ]
        return data

    def _extract_usage(self, usage) -> LLMUsage:
        if usage is None:
            raise LLMError("LLM response is missing usage statistics")
        try:
            input_tokens = usage.prompt_tokens
            output_tokens = usage.completion_tokens
            total_tokens = (
                usage.total_tokens
                if usage.total_tokens is not None
                else input_tokens + output_tokens
            )
            cost = round(
                input_tokens / 1_000_000 * self._input_price
                + output_tokens / 1_000_000 * self._output_price,
                6,
            )
        except (AttributeError, TypeError) as exc:
            raise LLMError(f"Unexpected LLM usage shape: {usage}") from exc
        return LLMUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost=cost,
        )
```

`chat()` 中：`messages=[message.model_dump() for message in messages]` 改为 `messages=[self._to_payload(m) for m in messages]`；原 usage 解析段（`usage = response.usage` 到 `return ChatResult(...)` 之前）替换为 `usage = self._extract_usage(response.usage)`，`ChatResult` 直接用 `usage=usage`。新增方法：

```python
    async def chat_with_tools(
        self, messages: list[ChatMessage], tools: list[dict]
    ) -> ToolChatResult:
        """Call chat completions with tools; return reply or tool calls."""
        if not self._api_key:
            raise LLMNotConfiguredError(
                "LLM API key is not configured. Set LLM_API_KEY in backend/.env."
            )
        client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=self._timeout_seconds,
        )
        try:
            response = await client.chat.completions.create(
                model=self._model,
                messages=[self._to_payload(m) for m in messages],
                tools=tools,
            )
        except APIError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        finally:
            await client.close()
        try:
            message = response.choices[0].message
            content = message.content
            raw_calls = message.tool_calls or []
            tool_calls = [
                ToolCall(id=c.id, name=c.function.name, arguments=c.function.arguments)
                for c in raw_calls
            ]
        except (AttributeError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected LLM response shape: {response}") from exc
        usage = self._extract_usage(response.usage)
        return ToolChatResult(
            content=content, tool_calls=tool_calls, model=self._model, usage=usage
        )
```

- [ ] **Step 5: 更新导出与公开 schema**

`backend/app/services/llm/__init__.py`：import 与 `__all__` 补充 `ToolCall`、`ToolChatResult`。

`backend/app/schemas/llm.py` 改为：

```python
"""Schemas for the LLM chat endpoint."""

from typing import Literal

from pydantic import BaseModel, Field

from app.services.llm.base import LLMUsage


class PublicChatMessage(BaseModel):
    """Public API message: tool roles are internal to the agent loop."""

    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """Payload for POST /api/llm/chat."""

    messages: list[PublicChatMessage] = Field(min_length=1)


class ChatResponse(BaseModel):
    """Reply text plus per-call token and cost statistics."""

    reply: str
    model: str
    usage: LLMUsage
```

`backend/app/api/routes/llm.py`：import 区加 `from app.services.llm.base import ChatMessage`（与现有 base import 合并），`chat()` 内调用改为：

```python
        result = await client.chat(
            [ChatMessage(role=m.role, content=m.content) for m in request.messages]
        )
```

- [ ] **Step 6: 运行全量测试确认通过**

Run: `pytest -q`
Expected: 全部 PASS（原有 24 项不回归 + 新增 7 项）

- [ ] **Step 7: 校验末尾换行并提交**

```powershell
git add backend/app/services/llm backend/app/schemas/llm.py backend/app/api/routes/llm.py backend/tests/test_llm_tools.py
git commit -m "feat: LLM 封装支持 tool calling，公开接口保持角色校验"
```

---

### Task 7: Agent 循环服务（tool 执行/事件/会话/轮次上限）

**Files:**
- Create: `backend/app/services/skills/agent.py`
- Create: `backend/tests/fakes.py`（共享 FakeLLM，Task 8/9 复用）
- Test: `backend/tests/test_skill_agent.py`

- [ ] **Step 1: 写 FakeLLM 与失败测试**

创建 `backend/tests/fakes.py`：

```python
"""Shared scripted fake LLM client for agent and eval tests."""

from app.services.llm.base import ChatResult, LLMUsage, ToolChatResult


def fake_usage(input_tokens: int = 100, output_tokens: int = 50) -> LLMUsage:
    return LLMUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        cost=0.00018,
    )


class FakeLLM:
    """Pops one scripted item per call; Exception items are raised."""

    def __init__(self, chat_replies=None, tool_replies=None):
        self.chat_replies = list(chat_replies or [])
        self.tool_replies = list(tool_replies or [])
        self.chat_calls: list = []
        self.tool_calls_received: list = []

    async def chat(self, messages):
        self.chat_calls.append(messages)
        if not self.chat_replies:
            return ChatResult(content="default reply", model="fake", usage=fake_usage())
        item = self.chat_replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return ChatResult(content=item, model="fake", usage=fake_usage())

    async def chat_with_tools(self, messages, tools):
        self.tool_calls_received.append(messages)
        if not self.tool_replies:
            return ToolChatResult(
                content="default reply", tool_calls=[], model="fake", usage=fake_usage()
            )
        item = self.tool_replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
```

创建 `backend/tests/test_skill_agent.py`：

```python
"""Tests for the agent loop using a scripted fake LLM."""

import asyncio

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
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_skill_agent.py -q`
Expected: FAIL（`ModuleNotFoundError: ... agent`）

- [ ] **Step 3: 实现 agent 服务**

创建 `backend/app/services/skills/agent.py`：

```python
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
        return self._loaded.get(session_id, set())

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
            except (SkillParseError, OSError) as exc:
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
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_skill_agent.py -q`
Expected: 6 passed

- [ ] **Step 5: 全量回归 + 校验末尾换行 + 提交**

Run: `pytest -q` → 全部 PASS

```powershell
git add backend/app/services/skills/agent.py backend/tests/fakes.py backend/tests/test_skill_agent.py
git commit -m "feat: Agent 循环支持 skill 加载、附带文件读取与事件记录"
```

---

### Task 8: 路由评测服务（计分/容错/缓存）

**Files:**
- Create: `backend/app/services/skills/evals.py`
- Test: `backend/tests/test_skill_evals.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_skill_evals.py`：

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_skill_evals.py -q`
Expected: FAIL（`ModuleNotFoundError: ... evals`）

- [ ] **Step 3: 实现评测服务**

创建 `backend/app/services/skills/evals.py`：

```python
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
    """Extract the first JSON object from a reply (tolerates code fences)."""
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"no JSON object in reply: {content!r}")
    data = json.loads(content[start : end + 1])
    action = data.get("action")
    if action not in {"load", "clarify", "none"}:
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
        cases = [EvalCase.model_validate_json(line) for line in lines if line.strip()]
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
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_skill_evals.py -q`
Expected: 5 passed

- [ ] **Step 5: 校验末尾换行并提交**

```powershell
git add backend/app/services/skills/evals.py backend/tests/test_skill_evals.py
git commit -m "feat: 路由评测服务支持分类计分与单条失败容错"
```

---

### Task 9: API 层（skills/agent/evals/debug 路由）

**Files:**
- Create: `backend/app/schemas/skills.py`
- Create: `backend/app/api/routes/skills.py`
- Create: `backend/app/api/routes/agent.py`
- Create: `backend/app/api/routes/evals.py`
- Modify: `backend/app/api/router.py`
- Test: `backend/tests/test_skills_api.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_skills_api.py`：

```python
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
    app = create_app()
    app.dependency_overrides[get_registry] = lambda: registry
    app.dependency_overrides[get_agent_service] = lambda: AgentService(registry, fake, 8)
    app.dependency_overrides[get_eval_service] = lambda: EvalService(registry, fake, eval_path)
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
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_skills_api.py -q`
Expected: FAIL（`ImportError: ... get_agent_service` 或 404）

- [ ] **Step 3: 实现 schemas 与路由**

创建 `backend/app/schemas/skills.py`：

```python
"""Schemas for skill listing, agent chat and debug endpoints."""

from pydantic import BaseModel, Field

from app.services.llm.base import LLMUsage
from app.services.skills.models import AgentEvent, ScanIssue


class SkillInfo(BaseModel):
    name: str
    description: str
    source_dir: str
    status: str
    overridden_by: str | None
    tokens: int
    loaded: bool


class InjectionInfo(BaseModel):
    tokens: int
    budget: int
    strategy: str
    skill_count: int


class SkillsResponse(BaseModel):
    skills: list[SkillInfo]
    injection: InjectionInfo
    issues: list[ScanIssue]


class SimulateRequest(BaseModel):
    enabled: bool


class AgentChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class AgentChatResponse(BaseModel):
    reply: str
    events: list[AgentEvent]
    usage: LLMUsage
    injection_tokens: int
    tool_rounds: int
```

创建 `backend/app/api/routes/skills.py`：

```python
"""Skill listing, rescan and debug simulate endpoints."""

from fastapi import APIRouter, Depends

from app.schemas.skills import InjectionInfo, SkillInfo, SkillsResponse, SimulateRequest
from app.services.skills.agent import AgentService, get_agent_service
from app.services.skills.injector import build_injection, count_tokens, skill_line
from app.services.skills.registry import SkillRegistry, get_registry

router = APIRouter(tags=["skills"])


def _build_response(
    registry: SkillRegistry, agent: AgentService, session_id: str | None
) -> SkillsResponse:
    records = registry.records
    injection = build_injection(records, registry.budget, registry.truncate_chars)
    loaded = agent.loaded_skills(session_id) if session_id else set()
    skills = [
        SkillInfo(
            name=r.name,
            description=r.description,
            source_dir=r.source_dir,
            status=r.status,
            overridden_by=r.overridden_by,
            tokens=count_tokens(skill_line(r)),
            loaded=r.name in loaded,
        )
        for r in records
    ]
    return SkillsResponse(
        skills=skills,
        injection=InjectionInfo(
            tokens=injection.tokens,
            budget=injection.budget,
            strategy=injection.strategy,
            skill_count=injection.skill_count,
        ),
        issues=registry.issues,
    )


@router.get("/skills", response_model=SkillsResponse)
async def list_skills(
    session_id: str | None = None,
    registry: SkillRegistry = Depends(get_registry),
    agent: AgentService = Depends(get_agent_service),
) -> SkillsResponse:
    registry.refresh()
    return _build_response(registry, agent, session_id)


@router.post("/skills/rescan", response_model=SkillsResponse)
async def rescan_skills(
    session_id: str | None = None,
    registry: SkillRegistry = Depends(get_registry),
    agent: AgentService = Depends(get_agent_service),
) -> SkillsResponse:
    registry.force_rescan()
    return _build_response(registry, agent, session_id)


@router.post("/debug/simulate", response_model=SkillsResponse)
async def toggle_simulate(
    request: SimulateRequest,
    session_id: str | None = None,
    registry: SkillRegistry = Depends(get_registry),
    agent: AgentService = Depends(get_agent_service),
) -> SkillsResponse:
    registry.set_simulate(request.enabled)
    return _build_response(registry, agent, session_id)
```

创建 `backend/app/api/routes/agent.py`：

```python
"""Agent chat endpoint running the tool-calling loop."""

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.skills import AgentChatRequest, AgentChatResponse
from app.services.llm.base import LLMError, LLMNotConfiguredError
from app.services.skills.agent import AgentService, get_agent_service

router = APIRouter(tags=["agent"])


@router.post("/agent/chat", response_model=AgentChatResponse)
async def agent_chat(
    request: AgentChatRequest,
    agent: AgentService = Depends(get_agent_service),
) -> AgentChatResponse:
    try:
        result = await agent.run_turn(request.session_id, request.message)
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return AgentChatResponse(
        reply=result.reply,
        events=result.events,
        usage=result.usage,
        injection_tokens=result.injection_tokens,
        tool_rounds=result.tool_rounds,
    )
```

创建 `backend/app/api/routes/evals.py`：

```python
"""Routing eval endpoints: run on demand, read cached results."""

from fastapi import APIRouter, Depends, HTTPException

from app.services.llm.base import LLMError, LLMNotConfiguredError
from app.services.skills.evals import EvalReport, EvalService, EvalSummary, get_eval_service

router = APIRouter(tags=["evals"])


@router.post("/evals/run", response_model=EvalReport)
async def run_evals(service: EvalService = Depends(get_eval_service)) -> EvalReport:
    try:
        return await service.run()
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/evals/results", response_model=EvalReport)
async def get_eval_results(service: EvalService = Depends(get_eval_service)) -> EvalReport:
    if service.last_report is None:
        return EvalReport(
            results=[], summary=EvalSummary(total=0, passed=0, accuracy=0.0, by_category={})
        )
    return service.last_report
```

`backend/app/api/router.py` 改为：

```python
"""Router aggregation.

- root_router: public endpoints mounted at "/" (e.g. /health).
- api_router: business endpoints mounted under "/api".
"""

from fastapi import APIRouter

from app.api.routes import agent, evals, health, llm, skills

root_router = APIRouter()
root_router.include_router(health.router)

api_router = APIRouter(prefix="/api")
api_router.include_router(llm.router)
api_router.include_router(skills.router)
api_router.include_router(agent.router)
api_router.include_router(evals.router)
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_skills_api.py -q`
Expected: 7 passed

- [ ] **Step 5: 全量回归 + 校验末尾换行 + 提交**

Run: `pytest -q` → 全部 PASS

```powershell
git add backend/app/schemas/skills.py backend/app/api/routes backend/app/api/router.py backend/tests/test_skills_api.py
git commit -m "feat: 新增 skills/agent/evals/debug API 路由"
```---

### Task 10: 前端类型与 API 层

**Files:**
- Create: `frontend/src/types/skill.ts`
- Create: `frontend/src/api/http.ts`
- Create: `frontend/src/api/skills.ts`
- Create: `frontend/src/api/agent.ts`
- Create: `frontend/src/api/evals.ts`

- [ ] **Step 1: 写类型定义**

创建 `frontend/src/types/skill.ts`：

```ts
// Types mirroring backend skill-system schemas.

export interface SkillInfo {
  name: string;
  description: string;
  source_dir: string;
  status: "active" | "overridden";
  overridden_by: string | null;
  tokens: number;
  loaded: boolean;
}

export interface InjectionInfo {
  tokens: number;
  budget: number;
  strategy: "full" | "truncated" | "names_only";
  skill_count: number;
}

export interface ScanIssue {
  path: string;
  reason: string;
}

export interface SkillsResponse {
  skills: SkillInfo[];
  injection: InjectionInfo;
  issues: ScanIssue[];
}

export interface AgentEvent {
  type: "load_skill" | "read_skill_file";
  skill: string;
  path: string | null;
  ok: boolean;
  error: string | null;
}

export interface LLMUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost: number;
}

export interface AgentChatResponse {
  reply: string;
  events: AgentEvent[];
  usage: LLMUsage;
  injection_tokens: number;
  tool_rounds: number;
}

export interface EvalActual {
  action: string;
  skill: string | null;
}

export interface EvalRow {
  id: number;
  query: string;
  category: string;
  expected_skill: string | null;
  actual: EvalActual | null;
  passed: boolean;
  error: string | null;
}

export interface EvalSummary {
  total: number;
  passed: number;
  accuracy: number;
  by_category: Record<string, { total: number; passed: number }>;
}

export interface EvalReport {
  results: EvalRow[];
  summary: EvalSummary;
}
```

- [ ] **Step 2: 写 API 层**

创建 `frontend/src/api/http.ts`：

```ts
// Shared JSON helpers. Components never call fetch directly.

export async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function postJson<T>(url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const data = await response.json();
      if (data.detail) detail = String(data.detail);
    } catch {
      // keep default detail when the error body is not JSON
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}
```

创建 `frontend/src/api/skills.ts`：

```ts
import type { SkillsResponse } from "../types/skill";
import { getJson, postJson } from "./http";

function sessionQuery(sessionId?: string): string {
  return sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
}

export function fetchSkills(sessionId?: string): Promise<SkillsResponse> {
  return getJson(`/api/skills${sessionQuery(sessionId)}`);
}

export function rescanSkills(sessionId?: string): Promise<SkillsResponse> {
  return postJson(`/api/skills/rescan${sessionQuery(sessionId)}`);
}

export function setSimulate(enabled: boolean, sessionId?: string): Promise<SkillsResponse> {
  return postJson(`/api/debug/simulate${sessionQuery(sessionId)}`, { enabled });
}
```

创建 `frontend/src/api/agent.ts`：

```ts
import type { AgentChatResponse } from "../types/skill";
import { postJson } from "./http";

export function sendChat(sessionId: string, message: string): Promise<AgentChatResponse> {
  return postJson("/api/agent/chat", { session_id: sessionId, message });
}
```

创建 `frontend/src/api/evals.ts`：

```ts
import type { EvalReport } from "../types/skill";
import { getJson, postJson } from "./http";

export function runEvals(): Promise<EvalReport> {
  return postJson("/api/evals/run");
}

export function fetchEvalResults(): Promise<EvalReport> {
  return getJson("/api/evals/results");
}
```

- [ ] **Step 3: 构建验证**

Run: `npm run build --prefix frontend`（在仓库根）或 frontend 目录 `npm run build`
Expected: 构建成功，无 TS 错误

- [ ] **Step 4: 校验末尾换行并提交**

```powershell
git add frontend/src/types/skill.ts frontend/src/api/http.ts frontend/src/api/skills.ts frontend/src/api/agent.ts frontend/src/api/evals.ts
git commit -m "feat: 前端 Skill 系统类型定义与 API 封装"
```

---

### Task 11: SkillList 与 DebugPanel 组件

**Files:**
- Create: `frontend/src/components/SkillList.vue`
- Create: `frontend/src/components/DebugPanel.vue`

- [ ] **Step 1: 实现 SkillList.vue**

创建 `frontend/src/components/SkillList.vue`：

```vue
<script setup lang="ts">
import type { SkillsResponse } from "../types/skill";

defineProps<{ data: SkillsResponse | null }>();

const sourceLabels: Record<string, string> = {
  skills: "内置",
  "skills-extra": "团队共享",
  synthetic: "模拟",
};

function sourceLabel(dir: string): string {
  return sourceLabels[dir] ?? dir;
}
</script>

<template>
  <section class="skill-list">
    <h2>Skill 列表</h2>
    <p v-if="!data" class="muted">加载中…</p>
    <template v-else>
      <ul>
        <li v-for="(skill, index) in data.skills" :key="`${index}-${skill.source_dir}/${skill.name}`"
            :class="{ overridden: skill.status === 'overridden' }">
          <div class="row">
            <strong>{{ skill.name }}</strong>
            <span class="tag">{{ sourceLabel(skill.source_dir) }}</span>
            <span v-if="skill.status === 'overridden'" class="tag warn">
              被覆盖 ← {{ skill.overridden_by }}
            </span>
            <span v-if="skill.loaded" class="tag ok">已加载</span>
            <span class="tokens">{{ skill.tokens }} tok</span>
          </div>
          <p class="desc">{{ skill.description }}</p>
        </li>
      </ul>
      <div v-if="data.issues.length" class="issues">
        <h3>跳过的 skill（{{ data.issues.length }}）</h3>
        <div v-for="issue in data.issues" :key="issue.path" class="issue">
          <code>{{ issue.path }}</code>
          <p>{{ issue.reason }}</p>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.skill-list ul { list-style: none; margin: 0; padding: 0; max-height: 45vh; overflow-y: auto; }
.skill-list li { border: 1px solid #ddd; border-radius: 6px; padding: 0.5rem 0.75rem; margin-bottom: 0.5rem; }
.skill-list li.overridden { opacity: 0.6; border-style: dashed; }
.row { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }
.tag { font-size: 0.72rem; border: 1px solid #bbb; border-radius: 4px; padding: 0 0.3rem; }
.tag.warn { color: #a05a00; border-color: #a05a00; }
.tag.ok { color: #1a7f37; border-color: #1a7f37; }
.tokens { margin-left: auto; font-size: 0.75rem; opacity: 0.7; }
.desc { margin: 0.3rem 0 0; font-size: 0.8rem; opacity: 0.75; }
.muted { opacity: 0.6; }
.issues { margin-top: 0.75rem; }
.issue { border-left: 3px solid #c0392b; padding-left: 0.5rem; margin-bottom: 0.5rem; font-size: 0.8rem; }
.issue code { word-break: break-all; }
.issue p { margin: 0.2rem 0 0; color: #c0392b; }
</style>
```

说明：同名冲突可能发生在同一目录内（同目录两个子目录同名时 `source_dir` 相同），组合 key 掺入 index 保证唯一；列表整体替换、项内无局部状态，index 参与 key 安全；`SkillInfo` 没有 `skill_path` 字段。

- [ ] **Step 2: 实现 DebugPanel.vue**

创建 `frontend/src/components/DebugPanel.vue`：

```vue
<script setup lang="ts">
import type { InjectionInfo } from "../types/skill";

const props = defineProps<{
  injection: InjectionInfo | null;
  simulating: boolean;
  busy: boolean;
}>();

const emit = defineEmits<{
  rescan: [];
  "toggle-simulate": [enabled: boolean];
}>();

function onToggle(e: Event) {
  const el = e.target as HTMLInputElement;
  emit("toggle-simulate", el.checked);
  // Reset the native checkbox to the controlled prop; on success the prop
  // change will drive the DOM, on failure this reverts the user's click.
  el.checked = props.simulating;
}

const strategyLabels: Record<string, string> = {
  full: "完整描述",
  truncated: "截断描述",
  names_only: "仅名字",
};
</script>

<template>
  <section class="debug-panel">
    <h2>调试面板</h2>
    <div class="controls">
      <button :disabled="busy" @click="emit('rescan')">重新扫描</button>
      <label class="switch">
        <input
          type="checkbox"
          :checked="simulating"
          :disabled="busy"
          @change="onToggle"
        />
        模拟 200 个 skill
      </label>
    </div>
    <dl v-if="injection" class="stats">
      <div><dt>注入 token（估算）</dt><dd>{{ injection.tokens }} / {{ injection.budget }}</dd></div>
      <div><dt>降级档位</dt><dd>{{ strategyLabels[injection.strategy] ?? injection.strategy }}</dd></div>
      <div><dt>参与注入 skill 数</dt><dd>{{ injection.skill_count }}</dd></div>
    </dl>
  </section>
</template>

<style scoped>
.debug-panel { border-top: 1px solid #ddd; padding-top: 0.75rem; margin-top: 0.75rem; }
.controls { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
button { padding: 0.35rem 0.9rem; cursor: pointer; }
.switch { display: flex; gap: 0.35rem; align-items: center; font-size: 0.85rem; }
.stats { margin: 0.75rem 0 0; font-size: 0.85rem; }
.stats div { display: flex; justify-content: space-between; padding: 0.15rem 0; }
.stats dt { opacity: 0.7; }
.stats dd { margin: 0; font-variant-numeric: tabular-nums; }
</style>
```

- [ ] **Step 3: 构建验证**

Run: frontend 目录 `npm run build`
Expected: 构建成功（组件尚未被引用，仅验证语法与类型）

- [ ] **Step 4: 校验末尾换行并提交**

```powershell
git add frontend/src/components/SkillList.vue frontend/src/components/DebugPanel.vue
git commit -m "feat: Skill 列表与调试面板组件"
```

---

### Task 12: ChatPanel、EvalTable 与双栏布局

**Files:**
- Create: `frontend/src/components/ChatPanel.vue`
- Create: `frontend/src/components/EvalTable.vue`
- Modify: `frontend/src/App.vue`（整体替换为双栏布局）

- [ ] **Step 1: 实现 ChatPanel.vue**

创建 `frontend/src/components/ChatPanel.vue`：

```vue
<script setup lang="ts">
import { ref } from "vue";
import { sendChat } from "../api/agent";
import type { AgentChatResponse } from "../types/skill";

const props = defineProps<{ sessionId: string }>();
const emit = defineEmits<{ "turn-complete": [] }>();

interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  meta?: AgentChatResponse;
  error?: boolean;
}

const turns = ref<ChatTurn[]>([]);
const input = ref("");
const status = ref<"idle" | "loading">("idle");

async function submit() {
  const message = input.value.trim();
  if (!message || status.value === "loading") return;
  turns.value.push({ role: "user", content: message });
  input.value = "";
  status.value = "loading";
  try {
    const result = await sendChat(props.sessionId, message);
    turns.value.push({ role: "assistant", content: result.reply, meta: result });
    emit("turn-complete");
  } catch (err) {
    turns.value.push({
      role: "assistant",
      content: err instanceof Error ? err.message : String(err),
      error: true,
    });
  } finally {
    status.value = "idle";
  }
}
</script>

<template>
  <section class="chat-panel">
    <h2>对话</h2>
    <div class="turns">
      <p v-if="!turns.length" class="muted">
        试试：「写一个 8 集的逆袭短剧剧本」或「帮我写这次提交的 commit message」
      </p>
      <div v-for="(turn, index) in turns" :key="index" :class="['turn', turn.role, { error: turn.error }]">
        <p class="content">{{ turn.content }}</p>
        <div v-if="turn.meta" class="meta">
          <span v-for="(event, i) in turn.meta.events" :key="i"
                :class="['chip', { fail: !event.ok }]">
            {{ event.type === "load_skill" ? "加载 skill" : "读取文件" }}:
            {{ event.skill }}<template v-if="event.path"> / {{ event.path }}</template>
            <template v-if="!event.ok">（{{ event.error }}）</template>
          </span>
          <span class="usage">
            注入 {{ turn.meta.injection_tokens }} tok · 本轮 {{ turn.meta.usage.total_tokens }} tok
            · ¥{{ turn.meta.usage.cost.toFixed(6) }} · tool 轮次 {{ turn.meta.tool_rounds }}
          </span>
        </div>
      </div>
      <p v-if="status === 'loading'" class="muted">思考中…</p>
    </div>
    <form class="composer" @submit.prevent="submit">
      <input v-model="input" :disabled="status === 'loading'" placeholder="输入请求…" />
      <button type="submit" :disabled="status === 'loading' || !input.trim()">发送</button>
    </form>
  </section>
</template>

<style scoped>
.chat-panel { display: flex; flex-direction: column; }
.turns { min-height: 200px; max-height: 45vh; overflow-y: auto; display: flex; flex-direction: column; gap: 0.5rem; }
.turn { border-radius: 8px; padding: 0.5rem 0.75rem; max-width: 90%; }
.turn.user { align-self: flex-end; background: #e8f0fe; }
.turn.assistant { align-self: flex-start; background: #f4f4f4; }
.turn.error { background: #fdecea; color: #c0392b; }
.content { margin: 0; white-space: pre-wrap; }
.meta { margin-top: 0.4rem; display: flex; flex-wrap: wrap; gap: 0.3rem; align-items: center; }
.chip { font-size: 0.72rem; border: 1px solid #1a7f37; color: #1a7f37; border-radius: 4px; padding: 0 0.3rem; }
.chip.fail { border-color: #c0392b; color: #c0392b; }
.usage { font-size: 0.72rem; opacity: 0.65; }
.composer { display: flex; gap: 0.5rem; margin-top: 0.75rem; }
.composer input { flex: 1; padding: 0.45rem 0.6rem; }
.composer button { padding: 0.45rem 1rem; cursor: pointer; }
.muted { opacity: 0.6; font-size: 0.85rem; }
</style>
```

- [ ] **Step 2: 实现 EvalTable.vue**

创建 `frontend/src/components/EvalTable.vue`：

```vue
<script setup lang="ts">
import { onMounted, ref } from "vue";
import { fetchEvalResults, runEvals } from "../api/evals";
import type { EvalReport } from "../types/skill";

const report = ref<EvalReport | null>(null);
const status = ref<"idle" | "loading" | "error">("idle");
const errorMessage = ref("");

onMounted(async () => {
  try {
    report.value = await fetchEvalResults();
  } catch {
    // cached results are optional on first load
  }
});

async function run() {
  status.value = "loading";
  errorMessage.value = "";
  try {
    report.value = await runEvals();
    status.value = "idle";
  } catch (err) {
    status.value = "error";
    errorMessage.value = err instanceof Error ? err.message : String(err);
  }
}
</script>

<template>
  <section class="eval-table">
    <div class="header">
      <h2>路由评测</h2>
      <button :disabled="status === 'loading'" @click="run">
        {{ status === "loading" ? "评测中（20 条真实调用）…" : "运行评测" }}
      </button>
    </div>
    <p v-if="status === 'error'" class="error">{{ errorMessage }}</p>
    <template v-if="report && report.results.length">
      <p class="summary">
        通过 {{ report.summary.passed }} / {{ report.summary.total }}
        （{{ (report.summary.accuracy * 100).toFixed(1) }}%）
        <span v-for="(bucket, category) in report.summary.by_category" :key="category" class="cat">
          {{ category }}: {{ bucket.passed }}/{{ bucket.total }}
        </span>
      </p>
      <table>
        <thead>
          <tr><th>#</th><th>请求</th><th>类别</th><th>期望</th><th>实际</th><th>结果</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in report.results" :key="row.id">
            <td>{{ row.id }}</td>
            <td class="query">{{ row.query }}</td>
            <td>{{ row.category }}</td>
            <td>{{ row.expected_skill ?? "（无/澄清）" }}</td>
            <td>
              <template v-if="row.actual">{{ row.actual.action }}<template v-if="row.actual.skill">: {{ row.actual.skill }}</template></template>
              <template v-else>error</template>
            </td>
            <td :class="row.passed ? 'pass' : 'fail'">{{ row.passed ? "✓" : "✗" }}</td>
          </tr>
        </tbody>
      </table>
    </template>
    <p v-else-if="status !== 'loading'" class="muted">尚无评测结果，点击「运行评测」发起 20 条真实路由评测。</p>
  </section>
</template>

<style scoped>
.eval-table { border-top: 1px solid #ddd; margin-top: 1rem; padding-top: 0.75rem; }
.header { display: flex; align-items: center; justify-content: space-between; }
.header button { padding: 0.35rem 0.9rem; cursor: pointer; }
.summary { font-size: 0.85rem; }
.cat { margin-left: 0.6rem; opacity: 0.7; }
table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
th, td { border-bottom: 1px solid #eee; padding: 0.3rem 0.4rem; text-align: left; }
.query { max-width: 320px; }
.pass { color: #1a7f37; font-weight: bold; }
.fail { color: #c0392b; font-weight: bold; }
.error { color: #c0392b; }
.muted { opacity: 0.6; font-size: 0.85rem; }
</style>
```

- [ ] **Step 3: 改造 App.vue**

`frontend/src/App.vue` 整体替换为：

```vue
<script setup lang="ts">
import { onMounted, ref } from "vue";
import HealthStatus from "./components/HealthStatus.vue";
import SkillList from "./components/SkillList.vue";
import DebugPanel from "./components/DebugPanel.vue";
import ChatPanel from "./components/ChatPanel.vue";
import EvalTable from "./components/EvalTable.vue";
import { fetchSkills, rescanSkills, setSimulate } from "./api/skills";
import type { SkillsResponse } from "./types/skill";

const sessionId = crypto.randomUUID();
const skillsData = ref<SkillsResponse | null>(null);
const simulating = ref(false);
const busy = ref(false);
const loadError = ref("");

async function refresh() {
  try {
    skillsData.value = await fetchSkills(sessionId);
    loadError.value = "";
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : String(err);
  }
}

async function handleRescan() {
  busy.value = true;
  try {
    skillsData.value = await rescanSkills(sessionId);
  } finally {
    busy.value = false;
  }
}

async function handleSimulate(enabled: boolean) {
  busy.value = true;
  try {
    skillsData.value = await setSimulate(enabled, sessionId);
    simulating.value = enabled;
  } finally {
    busy.value = false;
  }
}

onMounted(refresh);
</script>

<template>
  <header>
    <div>
      <h1>skill-find</h1>
      <p class="subtitle">Skill 系统演示：发现 · 注入 · 按需加载 · 热更新</p>
    </div>
    <HealthStatus />
  </header>
  <p v-if="loadError" class="load-error">Skill 列表加载失败：{{ loadError }}</p>
  <main class="layout">
    <aside>
      <SkillList :data="skillsData" />
      <DebugPanel
        :injection="skillsData?.injection ?? null"
        :simulating="simulating"
        :busy="busy"
        @rescan="handleRescan"
        @toggle-simulate="handleSimulate"
      />
    </aside>
    <section class="right">
      <ChatPanel :session-id="sessionId" @turn-complete="refresh" />
      <EvalTable />
    </section>
  </main>
</template>

<style scoped>
header { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; }
h1 { margin: 0 0 0.25rem; font-size: 1.75rem; }
.subtitle { margin: 0 0 1rem; opacity: 0.65; }
.layout { display: grid; grid-template-columns: 360px 1fr; gap: 1.5rem; align-items: start; }
.load-error { color: #c0392b; }
@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
}
</style>
```

- [ ] **Step 4: 构建验证**

Run: frontend 目录 `npm run build`
Expected: 构建成功，无 TS 错误

- [ ] **Step 5: 校验末尾换行并提交**

```powershell
git add frontend/src/components/ChatPanel.vue frontend/src/components/EvalTable.vue frontend/src/App.vue
git commit -m "feat: 对话面板、评测表格与左右双栏演示布局"
```

---

### Task 13: 全量验证与收尾

**Files:**
- Modify: `README.md`（追加 Skill 系统演示说明）
- 无新代码文件

- [ ] **Step 1: 后端全量测试**

Run: backend 目录 `.venv\Scripts\python.exe -m pytest -q`
Expected: 全部 PASS（约 75 项），0 failed

- [ ] **Step 2: 锁文件校验**

Run: backend 目录 `uv lock --check`
Expected: 退出码 0

- [ ] **Step 3: 前端构建**

Run: frontend 目录 `npm run build`
Expected: 构建成功

- [ ] **Step 4: 端到端手工验证（真实 LLM，费用由用户确认）**

启动：仓库根 `python dev.py`（后端 8000 / 前端 5173），浏览器打开 `http://localhost:5173`，逐项验证：

1. 左栏显示 6 个 active skill + 1 个被覆盖的 `short-drama-script`（标记「被覆盖 ← skills」）+ issues 区块显示 `broken-frontmatter-demo` 的解析错误原因；
2. 对话输入「写一个 8 集的逆袭短剧剧本，女主是被公司开除的销售」→ 回复下方出现「加载 skill: short-drama-script」chip，左栏该 skill 出现「已加载」；追问进入逐集写作后应出现「读取文件: … templates/script-template.md」chip；
3. 对话输入「读取 short-drama-script 的 ../ 外部文件」类请求（或诱导模型读越界路径）→ 失败 chip 标红，服务不崩溃；
4. 修改 `skills/csv-data-cleaning/SKILL.md` 的 description 并保存 → 不重启，直接发下一轮对话/刷新列表 → 新描述生效；
5. 点「重新扫描」→ 列表与注入统计刷新；
6. 打开「模拟 200 个 skill」→ 列表出现 200 个 synthetic 项，调试面板档位变为「仅名字」，token 数降到预算内；关闭后恢复「完整描述」；
7. 点「运行评测」→ 20 行结果逐条显示，含类别汇总正确率；刷新页面后结果仍在（内存缓存）。

任何一步不符合预期 → 回到对应任务修复并补测试。

- [ ] **Step 5: README 追加演示说明**

`README.md` 末尾追加：

```markdown
## Skill 系统演示

- 启动：`python dev.py`，打开 http://localhost:5173
- 左栏：skill 列表（来源/覆盖/token/加载状态）+ 调试面板（重新扫描、模拟 200 个 skill、注入预算与降级档位）
- 右栏：对话窗口（每轮展示加载的 skill 与读取的附带文件、token 与费用）+ 路由评测表（20 条，按钮触发真实评测）
- Skill 目录优先级：`skills/` > `skills-extra/`（先注册者胜，被覆盖者显式标记）
- 热更新：修改 SKILL.md 后下一轮对话即生效，无需重启
- 注入长度控制：预算 `SKILL_INJECTION_TOKEN_BUDGET`（默认 2000 token），超限自动降级 完整描述 → 截断描述 → 仅名字
- token 数为 tiktoken(cl100k_base) 估算值
```

- [ ] **Step 6: 提交收尾**

```powershell
git add README.md
git commit -m "docs: README 补充 Skill 系统演示说明"
```

---

## 计划自审记录

- **规格覆盖**：发现/容错（Task 2）、冲突（Task 2）、注入与长度控制（Task 3、5、9）、load_skill/read_skill_file 与防穿越（Task 4、7）、热更新（Task 5、7）、LLM tool-calling（Task 6）、评测（Task 8、9）、演示页面四区块（Task 11、12）、配置与依赖（Task 1）、端到端验证（Task 13）——规格 9 节全部有对应任务。
- **类型一致性**：`SkillRegistry(dirs, budget, truncate_chars)`、`AgentService(registry, client, max_tool_rounds)`、`EvalService(registry, client, eval_path)`、`build_injection(records, budget, truncate_chars)`、`read_skill_file(record, path)`、`FakeLLM(chat_replies, tool_replies)` 在各任务间签名一致；前端类型与后端 schema 字段一一对应。
- **兼容性**：`/api/llm/chat` 公开 role 校验经 `PublicChatMessage` 保留（现有 422 测试不回归）；`chat()` payload 形状经 `_to_payload` 保持不变（现有 payload 断言不回归）。
