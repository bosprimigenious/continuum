"""Basic publication hygiene, not comprehensive secret detection or a security audit."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
paths = (
    subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    )
    .decode()
    .split("\0")
)
patterns = [
    re.compile(r"/(?:Users|home)/[A-Za-z0-9_.-]+/"),
    re.compile(r"gh[pousr]_" + r"[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN " + r"(?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
]
bad = []
for name in sorted(set(filter(None, paths))):
    path = ROOT / name
    if path.is_symlink():
        bad.append((name, "symlink"))
        continue
    if not path.is_file():
        continue
    if path.suffix in {".db", ".sqlite", ".sqlite3", ".jsonl", ".tar", ".gz", ".zip"}:
        bad.append((name, "private-data/archive file type"))
    if path.name == ".env" or path.name.startswith(".env."):
        bad.append((name, "environment file"))
    if path.suffix.lower() in {".png", ".ico", ".icns", ".jpg", ".jpeg", ".webp"}:
        continue
    content = path.read_text(encoding="utf-8")
    if any(pattern.search(content) for pattern in patterns):
        bad.append((name, "possible private path/credential"))
if bad:
    for name, reason in bad:
        print(f"BLOCKED: {name}: {reason}")  # Never echo matched secret content.
    raise SystemExit(1)
print(f"PASS: basic publication hygiene ({len(set(filter(None, paths)))} files)")
