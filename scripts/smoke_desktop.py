"""Smoke a built Tauri package: bundled sidecar query, Windows GUI start.

Not part of the foundation gate. Does not scan home directories.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "synthetic.snapshot.json"
RELEASE = ROOT / "gui" / "src-tauri" / "target" / "release"


def _spawn_flags() -> dict[str, int]:
    if platform.system() == "Windows":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def run_cli(binary: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(binary), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
        **_spawn_flags(),
    )


def query_sidecar(binary: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        index = Path(tmp) / "index.db"
        imported = run_cli(binary, "--db", str(index), "--format", "json", "import", str(EXAMPLE))
        if imported.returncode:
            print(imported.stderr or imported.stdout)
            raise SystemExit(imported.returncode)
        payload = json.loads(imported.stdout)
        if payload.get("event_count") != 3:
            raise SystemExit(f"unexpected import: {payload}")
        search = run_cli(binary, "--db", str(index), "--format", "json", "search", "数据库锁")
        if search.returncode:
            print(search.stderr or search.stdout)
            raise SystemExit(search.returncode)
        items = json.loads(search.stdout).get("items") or []
        if not items:
            raise SystemExit("bundled sidecar search missed synthetic Chinese query")
        session_id = str(items[0].get("session_id") or "")
        read = run_cli(
            binary,
            "--db",
            str(index),
            "--format",
            "json",
            "read",
            session_id,
            "--limit",
            "20",
        )
        if read.returncode:
            print(read.stderr or read.stdout)
            raise SystemExit(read.returncode)
        events = json.loads(read.stdout).get("items") or []
        if len(events) != 3:
            raise SystemExit(f"bundled sidecar read expected 3 events, got {len(events)}")
    print(f"PASS: query {binary}")


def find_nsis() -> Path | None:
    folder = RELEASE / "bundle" / "nsis"
    if not folder.is_dir():
        return None
    matches = sorted(folder.glob("*.exe"))
    return matches[0] if matches else None


def find_gui() -> Path | None:
    # Windows is case-insensitive: Continuum.exe is the sidecar continuum.exe.
    for name in ("continuum-gui.exe", "Continuum"):
        path = RELEASE / name
        if path.is_file():
            return path
    app = RELEASE / "bundle" / "macos" / "Continuum.app" / "Contents" / "MacOS" / "Continuum"
    if app.is_file():
        return app
    return None


def sidecar_beside(gui: Path) -> Path | None:
    for name in ("continuum.exe", "continuum"):
        path = gui.parent / name
        if path.is_file():
            return path
    return None


def find_bundled_sidecar() -> Path | None:
    for path in (
        RELEASE / "continuum.exe",
        RELEASE / "continuum",
        RELEASE / "bundle" / "macos" / "Continuum.app" / "Contents" / "MacOS" / "continuum",
    ):
        if path.is_file():
            return path
    return None


def start_gui(exe: Path, seconds: float = 8.0) -> None:
    print(f"start {exe}")
    for child in sorted(exe.parent.iterdir()):
        print(f"  {child.name}")
    proc = subprocess.Popen(
        [str(exe)],
        cwd=str(exe.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    time.sleep(seconds)
    code = proc.poll()
    if code is not None:
        out, err = proc.communicate(timeout=5)
        print(out)
        print(err, file=sys.stderr)
        raise SystemExit(f"gui exited {code}")
    if platform.system() == "Windows":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            check=False,
            capture_output=True,
        )
    else:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    print(f"PASS: start {exe.name}")


def install_nsis(setup: Path) -> Path | None:
    subprocess.run([str(setup), "/S"], check=True, timeout=180, **_spawn_flags())
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return None
    base = Path(local)
    folders = (
        base / "Continuum",
        base / "Programs" / "Continuum",
        base / "com.github.bosprimigenious.continuum",
        base / "continuum-gui",
    )
    names = ("continuum-gui.exe",)
    for folder in folders:
        for name in names:
            path = folder / name
            if path.is_file():
                return path
    return None


def main() -> None:
    sidecar = find_bundled_sidecar()
    if sidecar is not None:
        query_sidecar(sidecar)
    else:
        sidecar_smoke = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "smoke_sidecar.py")],
            check=False,
        )
        if sidecar_smoke.returncode:
            raise SystemExit(sidecar_smoke.returncode)

    nsis = find_nsis()
    gui = find_gui()
    system = platform.system()
    if system == "Windows":
        if nsis is None and gui is None:
            raise SystemExit("missing Windows Continuum.exe / NSIS installer")
        if nsis is not None:
            print(f"nsis {nsis}")
            installed = install_nsis(nsis)
            if installed is not None:
                installed_sidecar = sidecar_beside(installed)
                if installed_sidecar is not None:
                    query_sidecar(installed_sidecar)
                start_gui(installed)
                return
        if gui is None:
            raise SystemExit("NSIS ran but Continuum.exe was not found")
        start_gui(gui)
        return
    if gui is not None:
        print(f"skip GUI start on {system}: {gui}")
    elif nsis is None:
        print(f"skip Windows installer on {system}")
    print("PASS: desktop smoke")


if __name__ == "__main__":
    main()
