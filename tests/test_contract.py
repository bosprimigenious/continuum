import json
import sqlite3
from pathlib import Path

import pytest

from continuum_history.adapters.snapshot import load_snapshot
from continuum_history.errors import HistoryError
from continuum_history.store import HistoryStore


@pytest.fixture
def snapshot_file(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_id": "demo",
                "sessions": [
                    {
                        "native_id": "session-a",
                        "title": "Synthetic database discussion",
                        "project": "example-project",
                        "events": [
                            {"native_id": "1", "role": "user", "text": "SQLite 数据库锁"},
                            {"native_id": "2", "role": "assistant", "text": "Use SQLite WAL."},
                            {"native_id": "3", "role": "user", "text": "100% literal_under"},
                            {"native_id": "4", "role": "assistant", "text": "Straße: 数据库锁"},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def store(tmp_path: Path, snapshot_file: Path) -> HistoryStore:
    store = HistoryStore(tmp_path / "index.sqlite3")
    store.replace_source(load_snapshot(snapshot_file))
    return store


def test_import_is_read_only_and_idempotent(store: HistoryStore, snapshot_file: Path) -> None:
    original = snapshot_file.read_bytes()
    before = store.sources()
    result = store.replace_source(load_snapshot(snapshot_file))
    assert result["changed"] is False
    assert store.sources() == before
    assert snapshot_file.read_bytes() == original
    assert before["items"][0]["event_count"] == 4


def test_read_every_event_without_truncation(store: HistoryStore) -> None:
    session_id = store.list_sessions()["items"][0]["id"]
    first = store.read(session_id, limit=2)
    second = store.read(session_id, limit=2, cursor=first["next_cursor"])
    assert [e["native_id"] for e in first["items"] + second["items"]] == ["1", "2", "3", "4"]
    assert first["next_cursor"]
    assert second["next_cursor"] is None
    assert first["items"][0]["source_ref"]


@pytest.mark.parametrize(
    ("query", "count"),
    [("sqlite", 2), ("数据库锁", 2), ("锁", 2), ("STRASSE", 1), ("%", 1), ("_", 1), ('"', 0)],
)
def test_literal_unicode_search(store: HistoryStore, query: str, count: int) -> None:
    assert len(store.search(query)["items"]) == count


def test_search_filters_before_pagination(store: HistoryStore) -> None:
    assert store.search("SQLite", source_id="other")["items"] == []
    assert store.search("SQLite", project="different")["items"] == []
    first = store.search("SQLite", project="example-project", limit=1)
    second = store.search("SQLite", project="example-project", limit=1, cursor=first["next_cursor"])
    assert len(first["items"]) == len(second["items"]) == 1
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert second["next_cursor"] is None


def test_cursor_is_bound_to_query_and_revision(store: HistoryStore, snapshot_file: Path) -> None:
    token = store.search("SQLite", limit=1)["next_cursor"]
    with pytest.raises(HistoryError, match="cursor"):
        store.search("锁", limit=1, cursor=token)
    snapshot = load_snapshot(snapshot_file)
    updated = snapshot.model_copy(update={"sessions": ()})
    store.replace_source(updated)
    with pytest.raises(HistoryError, match="stale_cursor"):
        store.search("SQLite", limit=1, cursor=token)
    assert store.search("SQLite")["items"] == []


def test_changed_snapshot_replaces_old_text(store: HistoryStore, snapshot_file: Path) -> None:
    data = json.loads(snapshot_file.read_text())
    data["sessions"][0]["events"][0]["text"] = "replacement text"
    snapshot_file.write_text(json.dumps(data))
    result = store.replace_source(load_snapshot(snapshot_file))
    assert result["changed"] is True
    assert len(store.search("SQLite")["items"]) == 1
    assert len(store.search("replacement")["items"]) == 1


def test_distinct_sources_preserve_identical_events(
    store: HistoryStore, snapshot_file: Path
) -> None:
    snapshot = load_snapshot(snapshot_file).model_copy(update={"source_id": "another"})
    store.replace_source(snapshot)
    matches = store.search("SQLite")["items"]
    assert len(matches) == 4
    assert len({item["id"] for item in matches}) == 4


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_invalid_page_size_is_rejected(store: HistoryStore, limit: int) -> None:
    with pytest.raises(HistoryError, match="invalid_limit"):
        store.list_sessions(limit=limit)


@pytest.mark.parametrize("cursor", ["garbage", "e30=", "W10=", "x" * 4097])
def test_invalid_cursor_is_not_empty_success(store: HistoryStore, cursor: str) -> None:
    with pytest.raises(HistoryError, match="invalid_cursor"):
        store.list_sessions(cursor=cursor)


def test_missing_session_is_not_empty_success(store: HistoryStore) -> None:
    with pytest.raises(HistoryError, match="not_found"):
        store.read("missing")


@pytest.mark.parametrize("query", ["", " ", "x" * 513, "\x00"])
def test_bad_query_is_rejected(store: HistoryStore, query: str) -> None:
    with pytest.raises(HistoryError, match="invalid_query"):
        store.search(query)


def test_malformed_snapshot_leaves_index_unchanged(
    store: HistoryStore, snapshot_file: Path
) -> None:
    before = store.sources()
    snapshot_file.write_text('{"schema_version":')
    with pytest.raises(HistoryError, match="invalid_snapshot"):
        store.replace_source(load_snapshot(snapshot_file))
    assert store.sources() == before


def test_duplicate_event_ids_are_rejected(snapshot_file: Path) -> None:
    data = json.loads(snapshot_file.read_text())
    data["sessions"][0]["events"][1]["native_id"] = "1"
    snapshot_file.write_text(json.dumps(data))
    with pytest.raises(HistoryError, match="invalid_snapshot"):
        load_snapshot(snapshot_file)


def test_future_database_schema_is_not_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(HistoryError, match="unsupported_schema"):
        HistoryStore(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 99
