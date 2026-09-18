import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from continuum_history.adapters.snapshot import load_snapshot
from continuum_history.errors import HistoryError
from continuum_history.store import HistoryStore

EXAMPLE = Path(__file__).parents[1] / "examples" / "synthetic.snapshot.json"


def test_unrelated_version_one_database_is_rejected_without_writes(tmp_path: Path) -> None:
    path = tmp_path / "unrelated.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE important (value TEXT)")
        db.execute("INSERT INTO important VALUES ('do not change')")
        db.execute("PRAGMA user_version=1")
    before = path.read_bytes()
    with pytest.raises(HistoryError, match="unsupported_schema"):
        HistoryStore(path)
    assert path.read_bytes() == before


def test_cursor_distinguishes_absent_filter_from_empty_filter(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "index.db")
    store.replace_source(load_snapshot(EXAMPLE))
    token = store.search("a", limit=1)["next_cursor"]
    assert token is not None
    with pytest.raises(HistoryError, match="invalid_cursor"):
        store.search("a", source_id="", limit=1, cursor=token)


def test_failed_refresh_rolls_back_all_derived_data(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path / "index.db")
    snapshot = load_snapshot(EXAMPLE)
    store.replace_source(snapshot)
    before = store.sources()
    with sqlite3.connect(store.path) as db:
        db.execute("""CREATE TRIGGER injected_failure BEFORE INSERT ON events
                      BEGIN SELECT RAISE(ABORT, 'injected failure'); END""")
    data = snapshot.model_dump()
    data["sessions"][0]["events"][0]["text"] = "must not survive rollback"
    updated = type(snapshot).model_validate(data)
    with pytest.raises(sqlite3.IntegrityError, match="injected failure"):
        store.replace_source(updated)
    assert store.sources() == before
    assert len(store.search("SQLite")["items"]) == 1
    assert not store.search("must not survive")["items"]


def test_long_text_can_be_read_in_full(tmp_path: Path) -> None:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    text = "begin " + "长" * 20000 + " end-marker"
    data["sessions"][0]["events"][0]["text"] = text
    from continuum_history.models import Snapshot

    store = HistoryStore(tmp_path / "index.db")
    store.replace_source(Snapshot.model_validate(data))
    hit = store.search("end-marker")["items"][0]
    assert hit["preview_truncated"]
    assert store.read(hit["session_id"])["items"][0]["text"] == text


def test_unknown_fields_and_duplicate_sessions_fail(tmp_path: Path) -> None:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["sessions"].append(data["sessions"][0])
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(HistoryError, match="invalid_snapshot"):
        load_snapshot(path)
    data["sessions"] = []
    data["unexpected"] = "must not be ignored"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(HistoryError, match="invalid_snapshot"):
        load_snapshot(path)


def test_oversized_input_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("continuum_history.adapters.snapshot.MAX_SNAPSHOT_BYTES", 10)
    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * 11)
    with pytest.raises(HistoryError, match="snapshot_too_large"):
        load_snapshot(path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits do not describe Windows ACLs")
def test_new_index_is_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "private.db"
    HistoryStore(path)
    assert path.stat().st_mode & 0o777 == 0o600


def test_nul_in_message_is_rejected_instead_of_silent_search_truncation(tmp_path: Path) -> None:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["sessions"][0]["events"][0]["text"] = "before\x00after"
    path = tmp_path / "nul.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(HistoryError, match="invalid_snapshot"):
        load_snapshot(path)


def test_stat_and_fstat_precision_difference_is_not_a_source_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = os.fstat

    def coarse_handle_stat(fd: int) -> SimpleNamespace:
        stat = original(fd)
        return SimpleNamespace(
            st_dev=stat.st_dev,
            st_ino=stat.st_ino,
            st_size=stat.st_size,
            st_mtime_ns=stat.st_mtime_ns // 1_000_000_000 * 1_000_000_000,
            st_ctime_ns=stat.st_ctime_ns // 1_000_000_000 * 1_000_000_000,
        )

    monkeypatch.setattr(os, "fstat", coarse_handle_stat)
    assert load_snapshot(EXAMPLE).source_id == "synthetic-demo"


def test_blocking_native_coverage_does_not_replace_index_or_invalidate_cursors(
    tmp_path: Path,
) -> None:
    from continuum_history.models import CoverageIssue, SnapshotCoverage

    store = HistoryStore(tmp_path / "index.db")
    snapshot = load_snapshot(EXAMPLE)
    store.replace_source(snapshot)
    before = store.sources()
    session_id = store.list_sessions()["items"][0]["id"]
    token = store.read(session_id, limit=1)["next_cursor"]
    assert token is not None
    damaged = snapshot.model_copy(
        update={
            "adapter": "cursor-state-vscdb-v1",
            "sessions": (),
            "coverage": SnapshotCoverage(
                adapter="cursor-state-vscdb-v1",
                format="cursor.global_state.vscdb.cursorDiskKV",
                observed_composer_data_version=13,
                observed_bubble_version=None,
                sessions_seen=1,
                sessions_imported=0,
                events_seen=0,
                events_imported=0,
                issues=(CoverageIssue(code="unknown_shape", native_session_id="session-x"),),
                complete=False,
            ),
        }
    )
    with pytest.raises(HistoryError, match="incomplete_source"):
        store.replace_source(damaged)
    assert store.sources() == before
    continued = store.read(session_id, limit=1, cursor=token)
    assert continued["items"][0]["native_id"] == "message-2"
    assert store.search("数据库锁")["items"]


def test_source_change_during_capture_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "changing.json"
    path.write_bytes(EXAMPLE.read_bytes())
    original = os.fstat
    calls = 0

    def changing_stat(fd: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        if calls == 2:
            with path.open("ab") as writer:
                writer.write(b" ")
        return original(fd)

    monkeypatch.setattr(os, "fstat", changing_stat)
    with pytest.raises(HistoryError, match="source_changed"):
        load_snapshot(path)
