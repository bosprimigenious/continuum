"""Spawn the published continuum CLI; never query SQLite or parse vendor files."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from continuum_history.errors import HistoryError

CLI_ARGV = (sys.executable, "-m", "continuum_history")


class CliBridge:
    def __init__(
        self, index: Path, *, argv: tuple[str, ...] = CLI_ARGV, timeout: float = 30
    ) -> None:
        self.index = index
        self.argv = argv
        self.timeout = timeout

    def run(self, *args: str, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        spawn: dict[str, Any] = {}
        if os.name == "nt":
            spawn["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            [*self.argv, "--db", str(self.index), "--format", "json", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=self.timeout,
            check=False,
            env=env,
            **spawn,
        )
        if result.returncode:
            raise HistoryError(_error_message(result.stderr))
        if not result.stdout.strip():
            return {}
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise HistoryError("cli_failed")
        return payload


def _error_message(stderr: str) -> str:
    if not stderr.strip():
        return "cli_failed"
    try:
        payload = json.loads(stderr)
    except json.JSONDecodeError:
        return "cli_failed"
    if isinstance(payload, dict) and payload.get("error"):
        return str(payload["error"])
    return "cli_failed"
