"""One-command dev launcher for skill-find.

Starts the FastAPI backend (uvicorn, port 8000) and the Vite dev server
(port 5173) together. Press Ctrl+C to stop both.

Usage: python dev.py
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"

BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://localhost:5173"


def resolve_python() -> str:
    """Prefer the backend/.venv interpreter, fall back to current one."""
    venv_python = BACKEND_DIR / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return str(venv_python) if venv_python.exists() else sys.executable


def resolve_npm() -> str:
    npm = shutil.which("npm")
    if npm is None:
        sys.exit("ERROR: npm not found on PATH. Install Node.js first.")
    return npm


def stop_process(proc: subprocess.Popen) -> None:
    """Terminate a child process (whole tree on Windows)."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> None:
    if not (FRONTEND_DIR / "node_modules").exists():
        sys.exit(
            "ERROR: frontend dependencies are missing.\n"
            "Run first: npm install --prefix frontend"
        )

    backend_cmd = [
        resolve_python(),
        "-m",
        "uvicorn",
        "app.main:app",
        "--reload",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
    frontend_cmd = [resolve_npm(), "run", "dev"]

    processes: list[subprocess.Popen] = []
    try:
        processes.append(subprocess.Popen(backend_cmd, cwd=BACKEND_DIR))
        processes.append(subprocess.Popen(frontend_cmd, cwd=FRONTEND_DIR))
        print(f"Backend:  {BACKEND_URL} (docs: {BACKEND_URL}/docs)")
        print(f"Frontend: {FRONTEND_URL}")
        print("Press Ctrl+C to stop both.")

        # Exit as soon as either process dies, so failures are visible.
        while True:
            for proc in processes:
                if proc.poll() is not None:
                    print(f"A dev process exited with code {proc.returncode}, shutting down.")
                    return
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping dev servers...")
    finally:
        for proc in processes:
            stop_process(proc)


if __name__ == "__main__":
    main()