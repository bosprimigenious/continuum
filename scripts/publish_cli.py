"""Local-token fallback for CLI/PyPI upload. Preferred path is GitHub OIDC.

The default publish architecture is `.github/workflows/publish.yml` with PyPI
Trusted Publishing. This script is only for an already-exported UV_PUBLISH_TOKEN
on a maintainer machine. It does not mint OIDC credentials.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if not os.environ.get("UV_PUBLISH_TOKEN"):
    print(
        "NOT READY: UV_PUBLISH_TOKEN is unset; refusing local upload. "
        "Preferred path: GitHub release → workflow publish.yml (OIDC). "
        "See docs/development.md.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def run(command: list[str]) -> None:
    print("\n>>> " + " ".join(command), flush=True)
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        print("NOT READY: CLI publish gate failed", file=sys.stderr)
        raise SystemExit(result.returncode)


run([sys.executable, "scripts/check.py"])
run([sys.executable, "scripts/release_check.py"])
distributions = sorted((ROOT / "dist").glob("continuum_history-*"))
if not distributions:
    print("NOT READY: dist/ has no continuum_history artifacts", file=sys.stderr)
    raise SystemExit(2)
run(["uv", "publish", *[str(path) for path in distributions]])
print("PASS: CLI distributions uploaded (native adapter and GUI remain unverified)")
