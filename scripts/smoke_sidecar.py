"""Smoke a built Tauri sidecar. Not part of the foundation gate."""

from __future__ import annotations

import json
import platform
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "synthetic.snapshot.json"


def sidecar_path() -> Path:
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Darwin" and machine in {"arm64", "aarch64"}:
        name = "continuum-aarch64-apple-darwin"
    elif system == "Darwin":
        name = "continuum-x86_64-apple-darwin"
    elif system == "Windows":
        name = "continuum-x86_64-pc-windows-msvc.exe"
    else:
        name = "continuum-x86_64-unknown-linux-gnu"
    path = ROOT / "gui" / "src-tauri" / "binaries" / name
    if not path.is_file():
        raise SystemExit(f"missing sidecar {path}; run scripts/build_sidecar.py")
    return path


def run(binary: Path, *args: str) -> subprocess.CompletedProcess[str]:
    spawn: dict[str, int] = {}
    if platform.system() == "Windows":
        spawn["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        [str(binary), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
        **spawn,
    )


def main() -> None:
    binary = sidecar_path()
    help_result = run(binary, "--help")
    if help_result.returncode:
        print(help_result.stderr or help_result.stdout)
        raise SystemExit(help_result.returncode)
    with tempfile.TemporaryDirectory() as tmp:
        index = Path(tmp) / "index.db"
        imported = run(binary, "--db", str(index), "--format", "json", "import", str(EXAMPLE))
        if imported.returncode:
            print(imported.stderr)
            raise SystemExit(imported.returncode)
        payload = json.loads(imported.stdout)
        if payload.get("event_count") != 3:
            raise SystemExit(f"unexpected import: {payload}")
        search = run(binary, "--db", str(index), "--format", "json", "search", "数据库锁")
        if search.returncode:
            print(search.stderr)
            raise SystemExit(search.returncode)
        items = json.loads(search.stdout).get("items") or []
        if not items:
            raise SystemExit("sidecar search missed synthetic Chinese query")
        session_id = items[0].get("session_id")
        if not session_id:
            raise SystemExit(f"search missing session_id: {items[0]}")
        read = run(
            binary,
            "--db",
            str(index),
            "--format",
            "json",
            "read",
            str(session_id),
            "--limit",
            "20",
        )
        if read.returncode:
            print(read.stderr)
            raise SystemExit(read.returncode)
        events = json.loads(read.stdout).get("items") or []
        if len(events) != 3:
            raise SystemExit(f"sidecar read expected 3 events, got {len(events)}")
    print(f"PASS: sidecar {binary.name}")


if __name__ == "__main__":
    main()
