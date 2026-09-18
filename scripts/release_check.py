"""CLI/PyPI release gate: inspect dist and refuse if the console script is missing."""

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
FORBIDDEN = (".sqlite", ".env")


def _one(pattern: str) -> Path:
    matches = sorted(DIST.glob(pattern))
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one {pattern} in dist; inspect stale build outputs")
    return matches[0]


wheel = _one("continuum_history-*.whl")
sdist = _one("continuum_history-*.tar.gz")
with zipfile.ZipFile(wheel) as archive:
    names = archive.namelist()
    if any(any(marker in name for marker in FORBIDDEN) for name in names):
        raise SystemExit("BLOCKED: wheel contains sqlite or env files")
    entry = next((name for name in names if name.endswith("entry_points.txt")), None)
    if entry is None:
        raise SystemExit("BLOCKED: wheel has no entry_points.txt")
    text = archive.read(entry).decode("utf-8")
    if "continuum = continuum_history.cli:main" not in text:
        raise SystemExit("BLOCKED: continuum console script is missing from the wheel")
print(f"PASS: CLI wheel {wheel.name}")
print(f"PASS: sdist {sdist.name}")
