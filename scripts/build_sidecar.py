"""Freeze continuum CLI as a Tauri sidecar. Not part of the foundation gate."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "src" / "continuum_history" / "__main__.py"
OUT_DIR = ROOT / "gui" / "src-tauri" / "binaries"


def target_triple() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Darwin" and machine in {"arm64", "aarch64"}:
        return "aarch64-apple-darwin"
    if system == "Darwin" and machine in {"x86_64", "amd64"}:
        return "x86_64-apple-darwin"
    if system == "Windows" and machine in {"amd64", "x86_64"}:
        return "x86_64-pc-windows-msvc"
    if system == "Linux" and machine in {"x86_64", "amd64"}:
        return "x86_64-unknown-linux-gnu"
    raise SystemExit(f"unsupported sidecar host: {system} {machine}")


def main() -> None:
    if not ENTRY.is_file():
        raise SystemExit(f"missing entry {ENTRY}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    triple = target_triple()
    work = ROOT / "build" / "sidecar"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        "continuum",
        "--distpath",
        str(work / "dist"),
        "--workpath",
        str(work / "work"),
        "--specpath",
        str(work),
        "--collect-all",
        "continuum_history",
        "--exclude-module",
        "mcp.cli",
        str(ENTRY),
    ]
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
    suffix = ".exe" if platform.system() == "Windows" else ""
    built = work / "dist" / f"continuum{suffix}"
    dest = OUT_DIR / f"continuum-{triple}{suffix}"
    shutil.copy2(built, dest)
    dest.chmod(dest.stat().st_mode | 0o111)
    print(f"PASS: sidecar {dest}")


if __name__ == "__main__":
    main()
