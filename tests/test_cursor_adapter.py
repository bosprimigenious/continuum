import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cursor_vscdb import (  # type: ignore[import-not-found]
    BUBBLE_ASSISTANT,
    BUBBLE_TOOLISH,
    BUBBLE_USER,
    COMPOSER_A,
    KNOWN_ASSISTANT_TEXT,
    KNOWN_USER_TEXT,
    PRIVATE_SENTINEL,
    SYNTHETIC_PROJECT,
    bubble_payload,
    composer_payload,
    long_conversation,
    put_kv,
    supported_conversation,
    write_state_vscdb,
)

from continuum_history.errors import HistoryError
from continuum_history.store import HistoryStore


def load_cursor(path: Path, source_id: str = "cursor-demo"):
    from continuum_history.adapters.cursor_state_vscdb import load_cursor_state_vscdb

    return load_cursor_state_vscdb(path, source_id=source_id)


def test_supported_bubbles_are_read_in_header_order_with_timestamps(tmp_path: Path) -> None:
    path = tmp_path / "state.vscdb"
    supported_conversation(path).close()
    snapshot = load_cursor(path)
    assert snapshot.adapter == "cursor-state-vscdb-v1"
    assert snapshot.source_id == "cursor-demo"
    assert len(snapshot.sessions) == 1
    session = snapshot.sessions[0]
    assert session.native_id == COMPOSER_A
    assert session.title == "Synthetic Cursor database discussion"
    assert session.project == SYNTHETIC_PROJECT
    expected_ts = datetime.fromtimestamp(1_737_316_260_000 / 1000, UTC).isoformat()
    assert session.created_at == expected_ts
    assert [event.native_id for event in session.events] == [
        BUBBLE_USER,
        BUBBLE_ASSISTANT,
        BUBBLE_TOOLISH,
    ]
    assert [event.role for event in session.events] == ["user", "assistant", "assistant"]
    assert session.events[0].text == KNOWN_USER_TEXT
    assert session.events[1].text == KNOWN_ASSISTANT_TEXT
    assert session.events[0].created_at == expected_ts
    assert PRIVATE_SENTINEL not in snapshot.model_dump_json()
    assert snapshot.coverage is not None
    assert snapshot.coverage.complete is False
    codes = {issue.code for issue in snapshot.coverage.issues}
    assert "unsupported_block" in codes


def test_sqlite_source_is_opened_read_only_and_left_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "state.vscdb"
    supported_conversation(path).close()
    before = path.read_bytes()
    wal, shm = Path(f"{path}-wal"), Path(f"{path}-shm")
    extras = {p: p.read_bytes() if p.exists() else None for p in (wal, shm)}
    load_cursor(path)
    assert path.read_bytes() == before
    for extra, content in extras.items():
        if content is None:
            assert not extra.exists()
        else:
            assert extra.read_bytes() == content
    from continuum_history.adapters.cursor_state_vscdb import connect_readonly

    with connect_readonly(path) as db:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute("INSERT INTO cursorDiskKV(key, value) VALUES ('x', '1')")


def test_wal_committed_rows_are_visible_without_checkpointing_source(tmp_path: Path) -> None:
    path = tmp_path / "state.vscdb"
    writer = supported_conversation(path, wal=True)
    try:
        mode = writer.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
        before = path.read_bytes()
        snapshot = load_cursor(path)
        assert snapshot.sessions[0].events[0].text == KNOWN_USER_TEXT
        assert path.read_bytes() == before
        assert writer.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        writer.close()


def test_source_change_during_capture_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.vscdb"
    supported_conversation(path).close()
    from continuum_history.adapters import cursor_state_vscdb as adapter

    original = adapter._fingerprint
    calls = 0

    def changing(target: Path) -> tuple[object, ...]:
        nonlocal calls
        calls += 1
        if calls == 2:
            with target.open("ab") as writer:
                writer.write(b"\0")
        return original(target)

    monkeypatch.setattr(adapter, "_fingerprint", changing)
    with pytest.raises(HistoryError, match="source_changed"):
        load_cursor(path)


def test_malformed_and_missing_records_are_visible_diagnostics(tmp_path: Path) -> None:
    path = tmp_path / "state.vscdb"
    missing = "00000000-0000-4000-8000-0000000000ff"
    duplicate = BUBBLE_USER
    headers = [
        {"bubbleId": BUBBLE_USER, "type": 1},
        {"bubbleId": duplicate, "type": 1},
        {"bubbleId": missing, "type": 2},
        {"bubbleId": "00000000-0000-4000-8000-0000000000ee", "type": 2},
    ]
    write_state_vscdb(
        path,
        composers=[
            (COMPOSER_A, composer_payload(COMPOSER_A, headers)),
            ("00000000-0000-4000-8000-0000000000bb", '{"composerId":'),
        ],
        bubbles=[
            (COMPOSER_A, BUBBLE_USER, bubble_payload(1, KNOWN_USER_TEXT)),
            (COMPOSER_A, "00000000-0000-4000-8000-0000000000ee", '{"type":2,'),
        ],
    ).close()
    snapshot = load_cursor(path)
    texts = [event.text for session in snapshot.sessions for event in session.events]
    assert KNOWN_USER_TEXT in texts
    assert snapshot.coverage is not None
    assert snapshot.coverage.complete is False
    codes = {issue.code for issue in snapshot.coverage.issues}
    assert {"malformed_record", "missing_bubble", "duplicate_event"} <= codes


def test_missing_optional_fields_still_import(tmp_path: Path) -> None:
    path = tmp_path / "state.vscdb"
    composer_id = "00000000-0000-4000-8000-0000000000cc"
    bubble_id = "00000000-0000-4000-8000-0000000000c1"
    payload = {
        "_v": 13,
        "composerId": composer_id,
        "fullConversationHeadersOnly": [{"bubbleId": bubble_id, "type": 1}],
    }
    write_state_vscdb(
        path,
        composers=[(composer_id, payload)],
        bubbles=[(composer_id, bubble_id, {"_v": 3, "type": 1})],
    ).close()
    snapshot = load_cursor(path)
    session = snapshot.sessions[0]
    assert session.title == ""
    assert session.project is None
    assert session.created_at is None
    assert session.events[0].text == ""
    assert session.events[0].created_at is None


def test_long_conversation_is_imported_and_readable_to_completion(tmp_path: Path) -> None:
    path = tmp_path / "state.vscdb"
    long_conversation(path, count=40)
    snapshot = load_cursor(path)
    assert len(snapshot.sessions[0].events) == 40
    store = HistoryStore(tmp_path / "index.sqlite3")
    store.replace_source(snapshot)
    session_id = store.list_sessions()["items"][0]["id"]
    seen: list[str] = []
    cursor = None
    while True:
        page = store.read(session_id, limit=7, cursor=cursor)
        seen.extend(item["native_id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [f"bubble-{i:04d}" for i in range(40)]
    hit = store.search("end-marker")["items"][0]
    assert hit["native_id"] == "bubble-0039"
    full = store.read(hit["session_id"], limit=40)
    assert full["next_cursor"] is None
    assert full["items"][-1]["text"].endswith("end-marker")


def test_repeat_import_does_not_add_events(tmp_path: Path) -> None:
    path = tmp_path / "state.vscdb"
    supported_conversation(path).close()
    store = HistoryStore(tmp_path / "index.sqlite3")
    first = store.replace_source(load_cursor(path))
    second = store.replace_source(load_cursor(path))
    assert first["changed"] is True
    assert second["changed"] is False
    assert first["event_count"] == 3
    sources = store.sources()
    assert sources["items"][0]["adapter"] == "cursor-state-vscdb-v1"
    assert sources["items"][0]["event_count"] == 3


def test_cli_cursor_import_requires_source_id(tmp_path: Path) -> None:
    path = tmp_path / "state.vscdb"
    supported_conversation(path).close()
    db = tmp_path / "index.sqlite3"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "continuum_history",
            "--db",
            str(db),
            "import",
            "--adapter",
            "cursor-state-vscdb",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert result.returncode == 2
    assert "source-id" in result.stderr
    assert not db.exists()


def test_cli_and_mcp_find_known_synthetic_message(tmp_path: Path) -> None:
    import asyncio

    from mcp import Client

    from continuum_history.mcp_server import create_server

    path = tmp_path / "state.vscdb"
    supported_conversation(path).close()
    db = tmp_path / "index.sqlite3"
    imported = subprocess.run(
        [
            sys.executable,
            "-m",
            "continuum_history",
            "--db",
            str(db),
            "import",
            "--adapter",
            "cursor-state-vscdb",
            "--source-id",
            "cursor-demo",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert imported.returncode == 0, imported.stderr

    store = HistoryStore(db)
    hits = store.search("数据库锁")["items"]
    assert hits
    assert hits[0]["preview"].startswith("How do we investigate")
    assert "continuum-snapshot://" in hits[0]["source_ref"]

    async def exercise() -> None:
        async with Client(create_server(store)) as client:
            sources = await client.call_tool("history_sources", {})
            assert sources.structured_content["items"][0]["adapter"] == "cursor-state-vscdb-v1"
            listed = await client.call_tool("history_list", {})
            assert listed.structured_content["items"][0]["native_id"] == COMPOSER_A
            found = await client.call_tool("history_search", {"query": "数据库锁"})
            assert found.structured_content["items"]
            sid = found.structured_content["items"][0]["session_id"]
            first = await client.call_tool("history_read", {"session_id": sid, "limit": 1})
            assert first.structured_content["items"][0]["text"] == KNOWN_USER_TEXT
            second = await client.call_tool(
                "history_read",
                {
                    "session_id": sid,
                    "limit": 10,
                    "cursor": first.structured_content["next_cursor"],
                },
            )
            assert {item["native_id"] for item in second.structured_content["items"]} == {
                BUBBLE_ASSISTANT,
                BUBBLE_TOOLISH,
            }
            assert second.structured_content["next_cursor"] is None

    asyncio.run(asyncio.wait_for(exercise(), timeout=10))


def test_missing_disk_kv_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "state.vscdb"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO ItemTable VALUES ('composer.composerData', '{}')")
    with pytest.raises(HistoryError, match="invalid_cursor_source"):
        load_cursor(path)


def test_adapter_does_not_open_home_cursor_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.vscdb"
    supported_conversation(path).close()
    home = tmp_path / "fake-home"
    home.mkdir()
    opened: list[str] = []
    real_connect = sqlite3.connect

    def tracing_connect(
        database: str | bytes, *args: object, **kwargs: object
    ) -> sqlite3.Connection:
        opened.append(str(database))
        return real_connect(database, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sqlite3, "connect", tracing_connect)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    load_cursor(path)
    assert opened
    for target in opened:
        assert "Library/Application Support/Cursor" not in target
        assert ".cursor" not in target
        assert str(home) not in target


def test_explicit_empty_headers_is_a_complete_empty_session(tmp_path: Path) -> None:
    path = tmp_path / "state.vscdb"
    write_state_vscdb(
        path,
        composers=[(COMPOSER_A, composer_payload(COMPOSER_A, []))],
        bubbles=[],
    ).close()
    snapshot = load_cursor(path)
    assert len(snapshot.sessions) == 1
    assert snapshot.sessions[0].events == ()
    assert snapshot.coverage is not None
    assert snapshot.coverage.issues == ()
    assert snapshot.coverage.complete is True
    assert snapshot.coverage.sessions_imported == 1
    HistoryStore(tmp_path / "index.sqlite3").replace_source(snapshot)


def test_missing_headers_is_unknown_shape_not_a_complete_empty_session(tmp_path: Path) -> None:
    path = tmp_path / "state.vscdb"
    write_state_vscdb(
        path,
        composers=[
            (
                COMPOSER_A,
                {"_v": 999, "composerId": COMPOSER_A, "name": "untitled"},
            )
        ],
        bubbles=[],
    ).close()
    snapshot = load_cursor(path)
    assert snapshot.sessions == ()
    assert snapshot.coverage is not None
    assert snapshot.coverage.complete is False
    assert snapshot.coverage.sessions_seen == 1
    assert snapshot.coverage.sessions_imported == 0
    assert {issue.code for issue in snapshot.coverage.issues} >= {"unknown_shape"}
    with pytest.raises(HistoryError, match="incomplete_source"):
        HistoryStore(tmp_path / "index.sqlite3").replace_source(snapshot)


def test_out_of_range_timestamp_is_unusable_not_an_overflow(tmp_path: Path) -> None:
    path = tmp_path / "state.vscdb"
    headers = [{"bubbleId": BUBBLE_USER, "type": 1}]
    write_state_vscdb(
        path,
        composers=[
            (COMPOSER_A, composer_payload(COMPOSER_A, headers, created_at=10**30)),
        ],
        bubbles=[
            (COMPOSER_A, BUBBLE_USER, bubble_payload(1, KNOWN_USER_TEXT, created_at=10**30)),
        ],
    ).close()
    snapshot = load_cursor(path)
    session = snapshot.sessions[0]
    assert session.events[0].text == KNOWN_USER_TEXT
    assert session.created_at is None
    assert session.updated_at is None
    assert session.events[0].created_at is None
    assert snapshot.coverage is not None
    assert snapshot.coverage.complete is False
    assert "unusable_timestamp" in {issue.code for issue in snapshot.coverage.issues}
    result = HistoryStore(tmp_path / "index.sqlite3").replace_source(snapshot)
    assert result["changed"] is True


def test_unrecognized_version_with_headers_imports_text_but_is_incomplete(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.vscdb"
    headers = [{"bubbleId": BUBBLE_USER, "type": 1}]
    write_state_vscdb(
        path,
        composers=[
            (COMPOSER_A, composer_payload(COMPOSER_A, headers, extra={"_v": 999})),
        ],
        bubbles=[
            (
                COMPOSER_A,
                BUBBLE_USER,
                bubble_payload(1, KNOWN_USER_TEXT, extra={"_v": 999}),
            ),
        ],
    ).close()
    snapshot = load_cursor(path)
    assert snapshot.sessions[0].events[0].text == KNOWN_USER_TEXT
    assert snapshot.coverage is not None
    assert snapshot.coverage.complete is False
    assert snapshot.coverage.observed_composer_data_version == 999
    assert "unrecognized_version" in {issue.code for issue in snapshot.coverage.issues}
    result = HistoryStore(tmp_path / "index.sqlite3").replace_source(snapshot)
    assert result["changed"] is True


def test_illegal_identity_is_blocking_and_not_imported(tmp_path: Path) -> None:
    path = tmp_path / "state.vscdb"
    composer_id = "c" * 300
    bubble_id = "b" * 300
    write_state_vscdb(
        path,
        composers=[
            (
                composer_id,
                {
                    "_v": 13,
                    "composerId": composer_id,
                    "name": "too long",
                    "fullConversationHeadersOnly": [{"bubbleId": bubble_id, "type": 1}],
                },
            )
        ],
        bubbles=[(composer_id, bubble_id, bubble_payload(1, KNOWN_USER_TEXT))],
    ).close()
    snapshot = load_cursor(path)
    assert snapshot.sessions == ()
    assert snapshot.coverage is not None
    assert snapshot.coverage.complete is False
    assert "illegal_identity" in {issue.code for issue in snapshot.coverage.issues}
    with pytest.raises(HistoryError, match="incomplete_source"):
        HistoryStore(tmp_path / "index.sqlite3").replace_source(snapshot)


def test_blocking_capture_preserves_revision_fts_and_cursors(tmp_path: Path) -> None:
    good = tmp_path / "good.vscdb"
    bad = tmp_path / "bad.vscdb"
    supported_conversation(good).close()
    write_state_vscdb(
        bad,
        composers=[(COMPOSER_A, {"_v": 999, "composerId": COMPOSER_A, "name": "x"})],
        bubbles=[],
    ).close()
    store = HistoryStore(tmp_path / "index.sqlite3")
    store.replace_source(load_cursor(good))
    before = store.sources()
    session_id = store.list_sessions()["items"][0]["id"]
    page = store.read(session_id, limit=1)
    token = page["next_cursor"]
    assert token is not None
    with pytest.raises(HistoryError, match="incomplete_source"):
        store.replace_source(load_cursor(bad))
    after = store.sources()
    assert after == before
    continued = store.read(session_id, limit=1, cursor=token)
    assert continued["items"][0]["native_id"] == BUBBLE_ASSISTANT
    hits = store.search("数据库锁")["items"]
    assert hits
    assert hits[0]["preview"].startswith("How do we investigate")
    again = store.replace_source(load_cursor(good))
    assert again["changed"] is False
    store.read(session_id, limit=1, cursor=token)


def test_cli_rejects_incomplete_source_before_creating_index(tmp_path: Path) -> None:
    path = tmp_path / "state.vscdb"
    db = tmp_path / "index.sqlite3"
    write_state_vscdb(
        path,
        composers=[(COMPOSER_A, {"_v": 999, "composerId": COMPOSER_A, "name": "x"})],
        bubbles=[],
    ).close()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "continuum_history",
            "--db",
            str(db),
            "import",
            "--adapter",
            "cursor-state-vscdb",
            "--source-id",
            "cursor-demo",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert result.returncode == 2
    assert "incomplete_source" in result.stderr
    assert path.as_posix() not in result.stderr
    assert not db.exists()


def test_sqlite_commit_during_capture_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.vscdb"
    writer = supported_conversation(path, wal=True)
    try:
        from continuum_history.adapters import cursor_state_vscdb as adapter

        original = adapter._fingerprint
        calls = 0

        def changing(target: Path) -> tuple[object, ...]:
            nonlocal calls
            calls += 1
            if calls == 2:
                put_kv(writer, f"composerData:{COMPOSER_A}", composer_payload(COMPOSER_A, []))
                writer.commit()
            return original(target)

        monkeypatch.setattr(adapter, "_fingerprint", changing)
        with pytest.raises(HistoryError, match="source_changed"):
            load_cursor(path)
    finally:
        writer.close()


def test_readonly_load_does_not_checkpoint_or_rewrite_wal_sidecars(tmp_path: Path) -> None:
    path = tmp_path / "state.vscdb"
    writer = supported_conversation(path, wal=True)
    try:
        wal, shm = Path(f"{path}-wal"), Path(f"{path}-shm")
        assert wal.exists()
        before_main = path.read_bytes()
        before_wal = wal.read_bytes()
        before_wal_size = wal.stat().st_size
        before_shm = shm.read_bytes() if shm.exists() else None
        snapshot = load_cursor(path)
        assert snapshot.sessions[0].events[0].text == KNOWN_USER_TEXT
        assert path.read_bytes() == before_main
        assert wal.read_bytes() == before_wal
        assert wal.stat().st_size == before_wal_size
        assert writer.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        if before_shm is None:
            assert not shm.exists()
        else:
            assert shm.read_bytes() == before_shm
    finally:
        writer.close()
