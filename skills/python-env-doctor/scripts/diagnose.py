#!/usr/bin/env python3
"""Collect a one-shot Python environment snapshot for diagnosis.

Run once at the start of diagnosis:
    python scripts/diagnose.py

Prints interpreter info, venv status, tool availability, key package
versions, and project manifest / lock file presence. Read-only: it
never installs, removes, or modifies anything.
"""

import importlib.metadata
import shutil
import subprocess
import sys
from pathlib import Path

KEY_PACKAGES = ["fastapi", "pydantic", "httpx", "openai", "pytest", "uvicorn"]


def tool_version(cmd: str) -> str:
    exe = shutil.which(cmd)
    if not exe:
        return "not found"
    try:
        out = subprocess.run(
            [exe, "--version"], capture_output=True, text=True, timeout=10
        )
        return (out.stdout or out.stderr).strip().splitlines()[0]
    except (OSError, subprocess.TimeoutExpired):
        return f"found at {exe}, but --version failed"


def main() -> None:
    print("== interpreter ==")
    print(f"executable: {sys.executable}")
    print(f"version: {sys.version.splitlines()[0]}")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    print(f"in venv: {in_venv} (prefix={sys.prefix})")

    print("\n== tools ==")
    for cmd in ("pip", "uv"):
        print(f"{cmd}: {tool_version(cmd)}")

    print("\n== key packages ==")
    for name in KEY_PACKAGES:
        try:
            print(f"{name}: {importlib.metadata.version(name)}")
        except importlib.metadata.PackageNotFoundError:
            print(f"{name}: not installed")

    print("\n== project files (cwd) ==")
    cwd = Path.cwd()
    for name in ("pyproject.toml", "uv.lock", "requirements.txt", ".venv"):
        print(f"{name}: {'present' if (cwd / name).exists() else 'absent'}")


if __name__ == "__main__":
    main()
