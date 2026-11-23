#!/usr/bin/env python3
"""Format and pacing checker for short-drama scripts.

Run only at the self-check stage:
    python scripts/check.py <script.md>

Checks per episode:
- scene headings match "### 场景 N：地点 - 日/夜 - 内/外"
- dialogue line count is within 8..15
- an ending hook marker "【本集结尾钩子】" exists and is non-empty
"""

import re
import sys
from pathlib import Path

EPISODE_RE = re.compile(r"^##\s+第\s*(\S+)\s*集", re.MULTILINE)
SCENE_RE = re.compile(r"^###\s+场景\s*\d+\s*[：:].+[-—–].+[-—–].+$", re.MULTILINE)
DIALOGUE_RE = re.compile(r"^[^\s#（(【].{0,12}[：:]\S", re.MULTILINE)
HOOK_RE = re.compile(r"【本集结尾钩子】\*{0,2}\s*[：:]\s*(\S.*)")


def check_episode(title: str, body: str) -> list[str]:
    issues: list[str] = []
    scenes = SCENE_RE.findall(body)
    if not scenes:
        issues.append(f"[{title}] no valid scene heading (### 场景 N：地点 - 日/夜 - 内/外)")
    lines = [
        ln for ln in body.splitlines()
        if DIALOGUE_RE.match(ln.strip()) and "【本集结尾钩子】" not in ln
    ]
    if not 8 <= len(lines) <= 15:
        issues.append(f"[{title}] dialogue count {len(lines)} outside 8..15")
    hook = HOOK_RE.search(body)
    if not hook or hook.group(1).strip().startswith("{"):
        issues.append(f"[{title}] missing or empty ending hook 【本集结尾钩子】")
    return issues


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python check.py <script.md>")
        return 2
    text = Path(sys.argv[1]).read_text(encoding="utf-8")
    marks = list(EPISODE_RE.finditer(text))
    if not marks:
        print("FAIL: no episode heading found (## 第 X 集)")
        return 1
    issues: list[str] = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        issues += check_episode(f"第{m.group(1)}集", text[m.start():end])
    if issues:
        print("\n".join(issues))
        print(f"FAIL: {len(issues)} issue(s)")
        return 1
    print(f"OK: {len(marks)} episode(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
