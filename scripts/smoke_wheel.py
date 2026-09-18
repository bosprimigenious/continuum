"""Run the built distribution outside the source tree in an isolated environment."""

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from cursor_vscdb import long_conversation  # noqa: E402

wheels = sorted((ROOT / "dist").glob("continuum_history-*.whl"))
if len(wheels) != 1:
    raise SystemExit("Expected exactly one wheel in dist; inspect stale build outputs manually")
wheel = wheels[0]
with zipfile.ZipFile(wheel) as archive:
    names = archive.namelist()
    assert "continuum_history/cli.py" in names
    assert not any(".sqlite" in name or ".env" in name for name in names)

code = r"""
import asyncio, importlib.metadata, json, shutil, subprocess, sys
from mcp import Client
from mcp.client.stdio import StdioServerParameters
import continuum_history
assert 'site-packages' in str(continuum_history.__file__)
cli = shutil.which('continuum')
assert cli, 'continuum console script missing from isolated install'
base = [cli, '--db', 'wheel-demo.db']
def run(*args):
    result = subprocess.run(base + list(args), check=True, capture_output=True, text=True,
                            encoding='utf-8', timeout=30)
    return json.loads(result.stdout)
source = sys.argv[1]
imported = run('import', '--adapter', 'cursor-state-vscdb', '--source-id', 'cursor-wheel', source)
assert imported['event_count'] == 40
again = run('import', '--adapter', 'cursor-state-vscdb', '--source-id', 'cursor-wheel', source)
assert again['changed'] is False
hit = run('search', '数据库锁')['items'][0]
assert '数据库锁' in hit['preview']

async def exercise():
    params = StdioServerParameters(command=cli, args=['--db', 'wheel-demo.db', 'serve'])
    async with Client(params) as client:
        assert {tool.name for tool in (await client.list_tools()).tools} == {
            'history_sources', 'history_list', 'history_search', 'history_read'
        }
        sources = await client.call_tool('history_sources', {})
        item = sources.structured_content['items'][0]
        assert item['adapter'] == 'cursor-state-vscdb-v1'
        assert item['coverage']
        seen = []
        cursor = None
        while True:
            arguments = {'session_id': hit['session_id'], 'limit': 7}
            if cursor:
                arguments['cursor'] = cursor
            page = await client.call_tool('history_read', arguments)
            assert not page.is_error, page.content
            seen.extend(page.structured_content['items'])
            cursor = page.structured_content['next_cursor']
            if cursor is None:
                break
        assert [event['native_id'] for event in seen] == [f'bubble-{i:04d}' for i in range(40)]
        assert seen[-1]['text'].endswith('end-marker')
        assert all(event['source_ref'] for event in seen)
        missing = await client.call_tool('history_read', {'session_id': 'missing'})
        assert missing.is_error
asyncio.run(exercise())
print('PASS: installed wheel', importlib.metadata.version('continuum-history'))
print('PASS: continuum CLI', cli)
print('PASS: cursor native wheel stdio')
"""
with tempfile.TemporaryDirectory(prefix="continuum-wheel-") as temporary:
    source = Path(temporary) / "state.vscdb"
    long_conversation(source, count=40)
    before = source.read_bytes()
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
            str(source),
        ],
        cwd=temporary,
        check=True,
        timeout=180,
    )
    assert source.read_bytes() == before, "isolated wheel import modified the Cursor fixture"
