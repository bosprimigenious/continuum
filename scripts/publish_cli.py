"""Upload the CLI wheel to PyPI. Fails closed without UV_PUBLISH_TOKEN."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if not os.environ.get("UV_PUBLISH_TOKEN"):
    print("NOT READY: UV_PUBLISH_TOKEN is unset; refusing to upload", file=sys.stderr)
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
