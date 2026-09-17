"""Run the built distribution outside the source tree in an isolated environment."""

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
wheels = sorted((ROOT / "dist").glob("continuum_history-*.whl"))
if len(wheels) != 1:
    raise SystemExit("Expected exactly one wheel in dist; inspect stale build outputs manually")
wheel = wheels[0]
with zipfile.ZipFile(wheel) as archive:
    names = archive.namelist()
    assert "continuum_history/cli.py" in names
    assert not any(".sqlite" in name or ".env" in name for name in names)

code = """
import importlib.metadata, json, pathlib, subprocess, sys
import continuum_history
assert 'site-packages' in str(continuum_history.__file__)
base = [sys.executable, '-I', '-m', 'continuum_history', '--db', 'wheel-demo.db']
def run(*args):
    result = subprocess.run(base + list(args), check=True, capture_output=True, text=True,
                            encoding='utf-8', timeout=20)
    return json.loads(result.stdout)
assert run('import', sys.argv[1])['event_count'] == 3
assert run('import', sys.argv[1])['changed'] is False
hit = run('search', '数据库锁')['items'][0]
assert len(run('read', hit['session_id'])['items']) == 3
print('PASS: installed wheel', importlib.metadata.version('continuum-history'))
"""
with tempfile.TemporaryDirectory(prefix="continuum-wheel-") as temporary:
    subprocess.run(
        [
            "uv",
            "run",
            "--isolated",
            "--no-project",
            "--python",
            sys.executable,
            "--with",
            str(wheel),
            "python",
            "-I",
            "-c",
            code,
            str(ROOT / "examples" / "synthetic.snapshot.json"),
        ],
        cwd=temporary,
        check=True,
        timeout=180,
    )
