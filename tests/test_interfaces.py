import asyncio
import json
import subprocess
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from continuum_history.adapters.snapshot import load_snapshot
from continuum_history.mcp_server import create_server
from continuum_history.store import HistoryStore

EXAMPLE = Path(__file__).parents[1] / "examples" / "synthetic.snapshot.json"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "continuum_history", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )


def test_cli_import_search_read_and_error(tmp_path: Path) -> None:
    db = str(tmp_path / "index.db")
    imported = run_cli("--db", db, "import", str(EXAMPLE))
    assert imported.returncode == 0, imported.stderr
    assert json.loads(imported.stdout)["event_count"] == 3
    repeated = run_cli("--db", db, "import", str(EXAMPLE))
    assert json.loads(repeated.stdout)["changed"] is False
    hit = json.loads(run_cli("--db", db, "search", "数据库锁").stdout)["items"][0]
    read = json.loads(run_cli("--db", db, "read", hit["session_id"], "--limit", "1").stdout)
    assert "SQLite" in read["items"][0]["text"]
    assert read["next_cursor"]
    assert json.loads(run_cli("--db", db, "sources").stdout)["items"]
    assert json.loads(run_cli("--db", db, "list").stdout)["items"]
    failure = run_cli("--db", db, "read", "missing")
    assert failure.returncode == 2
    assert not failure.stdout
    assert "not_found" in failure.stderr


def test_help_does_not_create_database(tmp_path: Path) -> None:
    db = tmp_path / "absent.db"
    result = run_cli("--db", str(db), "--help")
    assert result.returncode == 0
    assert not db.exists()


def test_invalid_import_does_not_create_database_or_echo_contents(tmp_path: Path) -> None:
    source, db = tmp_path / "bad.json", tmp_path / "absent.db"
    source.write_text('{"not-a-snapshot": "PRIVATE_SENTINEL"}', encoding="utf-8")
    result = run_cli("--db", str(db), "import", str(source))
    assert result.returncode == 2
    assert not db.exists()
    assert "PRIVATE_SENTINEL" not in result.stderr
    missing = run_cli("--db", str(db), "import", str(tmp_path / "missing.json"))
    assert missing.returncode == 2
    assert "FileNotFoundError" in missing.stderr


def test_real_stdio_mcp_roundtrip_matches_core(tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    store = HistoryStore(db)
    store.replace_source(load_snapshot(EXAMPLE))

    async def exercise() -> None:
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "continuum_history", "--db", str(db), "serve"]
        )
        async with Client(params) as client:
            listed = await client.list_tools()
            assert {tool.name for tool in listed.tools} == {
                "history_sources",
                "history_list",
                "history_search",
                "history_read",
            }
            assert all(tool.annotations.read_only_hint for tool in listed.tools)
            result = await client.call_tool("history_search", {"query": "数据库锁"})
            assert not result.is_error
            assert result.structured_content == store.search("数据库锁")
            for name, args, expected in [
                ("history_sources", {}, store.sources()),
                ("history_list", {"limit": 1}, store.list_sessions(limit=1)),
            ]:
                response = await client.call_tool(name, args)
                assert response.structured_content == expected
            sid = result.structured_content["items"][0]["session_id"]
            first = await client.call_tool("history_read", {"session_id": sid, "limit": 1})
            assert first.structured_content == store.read(sid, limit=1)
            second = await client.call_tool(
                "history_read",
                {"session_id": sid, "limit": 1, "cursor": first.structured_content["next_cursor"]},
            )
            assert second.structured_content["items"][0]["native_id"] == "message-2"
            bad = await client.call_tool("history_read", {"session_id": "../../private"})
            assert bad.is_error
            assert "not_found" in str(bad.content)
            bad = await client.call_tool("history_search", {"query": ""})
            assert bad.is_error
            assert "invalid_query" in str(bad.content)
            paged = await client.call_tool("history_search", {"query": "a", "limit": 1})
            store.replace_source(load_snapshot(EXAMPLE).model_copy(update={"sessions": ()}))
            stale = await client.call_tool(
                "history_search", {"query": "a", "cursor": paged.structured_content["next_cursor"]}
            )
            assert stale.is_error
            assert "stale_cursor" in str(stale.content)

    asyncio.run(asyncio.wait_for(exercise(), timeout=30))


def test_inprocess_mcp_facade_contract(tmp_path: Path) -> None:
    """Also exercise handlers in-process; stdio subprocess exits may not flush coverage."""
    store = HistoryStore(tmp_path / "index.db")
    store.replace_source(load_snapshot(EXAMPLE))

    async def exercise() -> None:
        async with Client(create_server(store)) as client:
            sid = store.list_sessions()["items"][0]["id"]
            calls = [
                ("history_sources", {}, store.sources()),
                ("history_list", {}, store.list_sessions()),
                ("history_search", {"query": "数据库锁"}, store.search("数据库锁")),
                ("history_read", {"session_id": sid}, store.read(sid)),
            ]
            for name, arguments, expected in calls:
                result = await client.call_tool(name, arguments)
                assert not result.is_error
                assert result.structured_content == expected
            failed = await client.call_tool("history_read", {"session_id": "missing"})
            assert failed.is_error
            assert "not_found" in str(failed.content)

    asyncio.run(asyncio.wait_for(exercise(), timeout=10))
