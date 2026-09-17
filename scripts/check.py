"""One cross-platform foundation gate. Stop at the first failed check."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = [
    [sys.executable, "-m", "ruff", "format", "--check", "."],
    [sys.executable, "-m", "ruff", "check", "."],
    [sys.executable, "-m", "mypy"],
    [sys.executable, "-m", "pytest", "--cov", "--cov-report=term-missing"],
    [sys.executable, "scripts/publication_check.py"],
    ["uv", "build"],
    [sys.executable, "scripts/smoke_wheel.py"],
]

for command in COMMANDS:
    print("\n>>> " + " ".join(command), flush=True)
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        print("NOT READY: foundation gate failed", file=sys.stderr)
        raise SystemExit(result.returncode)
print("PASS: foundation gate (native adapters, GUI and real hosts are NOT verified)")
