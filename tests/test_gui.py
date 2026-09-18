"""GUI talks to the index only through the continuum CLI JSON interface."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from cursor_vscdb import (  # type: ignore[import-not-found]
    COMPOSER_A,
    composer_payload,
    supported_conversation,
    write_state_vscdb,
)

from continuum_history.errors import HistoryError
from continuum_history.gui import GuiSession

EXAMPLE = Path(__file__).parents[1] / "examples" / "synthetic.snapshot.json"


def _snapshot(path: Path, *, source_id: str, events: list[dict[str, str]]) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_id": source_id,
                "sessions": [
                    {
                        "native_id": "gui-session",
                        "title": "GUI synthetic session",
                        "project": "example-project",
                        "events": events,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_empty_state_does_not_spawn_cli_or_scan_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("cli")),
    )
    monkeypatch.setattr(
        Path,
        "home",
        classmethod(lambda cls: (_ for _ in ()).throw(AssertionError("home"))),
    )
    session = GuiSession(tmp_path / "index.db")
    view = session.view()
    assert view["state"] == "empty"
    assert view["sources"] == []
    assert view["items"] == []
    assert view["error"] is None
    assert not (tmp_path / "index.db").exists()


def test_import_search_paginated_read_goes_through_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded: list[list[str]] = []
    real_run = subprocess.run

    def wrapped(
        command: object, *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if isinstance(command, (list, tuple)):
            recorded.append([str(part) for part in command])
        return real_run(command, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(subprocess, "run", wrapped)
    session = GuiSession(tmp_path / "index.db")
    session.select_source(EXAMPLE)
    imported = session.import_selected()
    assert imported["event_count"] == 3
    view = session.view()
    assert view["state"] == "ready"
    assert view["sources"][0]["coverage"]["status"] == "supplied_snapshot"
    hits = session.search("数据库锁")
    assert hits["items"]
    session_id = hits["items"][0]["session_id"]
    first = session.read(session_id, limit=1)
    assert "SQLite" in first["items"][0]["text"]
    assert first["next_cursor"]
    second = session.read(session_id, limit=1, cursor=first["next_cursor"])
    assert "WAL" in second["items"][0]["text"]
    rest = session.read(session_id, limit=1, cursor=second["next_cursor"])
    assert "保留原文" in rest["items"][0]["text"]
    assert rest["next_cursor"] is None
    assert any("-m" in cmd and "continuum_history" in cmd for cmd in recorded)
    assert all("HistoryStore" not in part for cmd in recorded for part in cmd)


def test_long_cjk_is_truncated_in_search_and_complete_in_read(tmp_path: Path) -> None:
    text = "锁" * 300
    source = _snapshot(
        tmp_path / "long.json",
        source_id="gui-cjk",
        events=[{"native_id": "1", "role": "user", "text": text}],
    )
    session = GuiSession(tmp_path / "index.db")
    session.select_source(source)
    session.import_selected()
    hit = session.search("锁锁锁")["items"][0]
    assert hit["preview_truncated"]
    assert hit["preview"] == "锁" * 240
    assert session.read(hit["session_id"])["items"][0]["text"] == text


def test_stale_cursor_is_an_error_not_empty_results(tmp_path: Path) -> None:
    source = _snapshot(
        tmp_path / "page.json",
        source_id="gui-page",
        events=[
            {"native_id": "1", "role": "user", "text": "分页标记 one"},
            {"native_id": "2", "role": "assistant", "text": "分页标记 two"},
            {"native_id": "3", "role": "user", "text": "分页标记 three"},
        ],
    )
    emptied = tmp_path / "empty.json"
    emptied.write_text(
        json.dumps({"schema_version": 1, "source_id": "gui-page", "sessions": []}),
        encoding="utf-8",
    )
    session = GuiSession(tmp_path / "index.db")
    session.select_source(source)
    session.import_selected()
    page = session.search("分页标记", limit=1)
    assert page["next_cursor"]
    session.select_source(emptied)
    session.refresh()
    with pytest.raises(HistoryError, match="stale_cursor"):
        session.search("分页标记", limit=1, cursor=page["next_cursor"])
    assert session.view()["state"] == "error"
    assert "stale_cursor" in str(session.view()["error"])
    recovered = session.search("分页标记")
    assert recovered["items"] == []
    assert session.view()["state"] == "ready"
    assert session.view()["error"] is None


def test_blocking_import_is_visible_and_recoverable(tmp_path: Path) -> None:
    payload = composer_payload(COMPOSER_A, [])
    del payload["fullConversationHeadersOnly"]
    broken = tmp_path / "state.vscdb"
    write_state_vscdb(broken, composers=[(COMPOSER_A, payload)]).close()
    session = GuiSession(tmp_path / "index.db")
    session.select_source(broken, adapter="cursor-state-vscdb", source_id="cursor-demo")
    with pytest.raises(HistoryError, match="incomplete_source"):
        session.import_selected()
    assert session.view()["state"] == "error"
    assert "incomplete_source" in str(session.view()["error"])
    assert not (tmp_path / "index.db").exists()
    session.select_source(EXAMPLE)
    session.import_selected()
    assert session.view()["state"] == "ready"
    assert session.search("数据库锁")["items"]


def test_native_coverage_gaps_are_shown_not_stuffed_into_results(tmp_path: Path) -> None:
    source = tmp_path / "state.vscdb"
    supported_conversation(source).close()
    session = GuiSession(tmp_path / "index.db")
    session.select_source(source, adapter="cursor-state-vscdb", source_id="cursor-demo")
    session.import_selected()
    coverage = session.view()["sources"][0]["coverage"]
    assert coverage["complete"] is False
    assert {issue["code"] for issue in coverage["issues"]} >= {"unsupported_block"}
    assert all("PRIVATE_SENTINEL" not in json.dumps(hit) for hit in session.search("WAL")["items"])


def test_search_and_list_before_import_stay_empty_without_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("cli")),
    )
    session = GuiSession(tmp_path / "index.db")
    listed = session.list_sessions()
    searched = session.search("数据库锁")
    assert listed["items"] == []
    assert searched["items"] == []
    assert session.view()["state"] == "empty"
    assert not (tmp_path / "index.db").exists()


def test_import_without_source_is_visible_error(tmp_path: Path) -> None:
    session = GuiSession(tmp_path / "index.db")
    with pytest.raises(HistoryError, match="invalid_import"):
        session.import_selected()
    assert session.view()["state"] == "error"
    assert "invalid_import" in str(session.view()["error"])
    assert not (tmp_path / "index.db").exists()


def test_list_sessions_then_read_without_search(tmp_path: Path) -> None:
    session = GuiSession(tmp_path / "index.db")
    session.select_source(EXAMPLE)
    session.import_selected()
    listed = session.list_sessions(limit=1)
    assert listed["items"][0]["title"]
    session_id = listed["items"][0]["id"]
    page = session.read(session_id, limit=2)
    assert len(page["items"]) == 2
    assert session.view()["events"] == page["items"]
    assert session.view()["next_read_cursor"] == page["next_cursor"]
    session.read(session_id, limit=2, cursor=page["next_cursor"])
    assert [event["native_id"] for event in session.view()["events"]] == [
        "message-1",
        "message-2",
        "message-3",
    ]
    assert session.view()["next_read_cursor"] is None


def test_search_pages_accumulate_until_new_query(tmp_path: Path) -> None:
    source = _snapshot(
        tmp_path / "page.json",
        source_id="gui-page",
        events=[
            {"native_id": "1", "role": "user", "text": "分页标记 one"},
            {"native_id": "2", "role": "assistant", "text": "分页标记 two"},
            {"native_id": "3", "role": "user", "text": "分页标记 three"},
        ],
    )
    session = GuiSession(tmp_path / "index.db")
    session.select_source(source)
    session.import_selected()
    first = session.search("分页标记", limit=1)
    assert len(session.view()["items"]) == 1
    assert session.view()["next_cursor"] == first["next_cursor"]
    session.search("分页标记", limit=1, cursor=first["next_cursor"])
    assert [hit["native_id"] for hit in session.view()["items"]] == ["1", "2"]
    session.search("分页标记 two")
    assert [hit["native_id"] for hit in session.view()["items"]] == ["2"]
    assert session.view()["next_cursor"] is None


def test_refresh_clears_results_and_cursors(tmp_path: Path) -> None:
    session = GuiSession(tmp_path / "index.db")
    session.select_source(EXAMPLE)
    session.import_selected()
    hit = session.search("数据库锁")["items"][0]
    session.read(hit["session_id"], limit=1)
    assert session.view()["items"]
    assert session.view()["events"]
    session.refresh()
    view = session.view()
    assert view["state"] == "ready"
    assert view["items"] == []
    assert view["events"] == []
    assert view["next_cursor"] is None
    assert view["next_read_cursor"] is None


def test_invalid_query_is_error_then_recoverable(tmp_path: Path) -> None:
    session = GuiSession(tmp_path / "index.db")
    session.select_source(EXAMPLE)
    session.import_selected()
    with pytest.raises(HistoryError, match="invalid_query"):
        session.search("")
    assert session.view()["state"] == "error"
    assert session.search("数据库锁")["items"]
    assert session.view()["state"] == "ready"
    assert session.view()["error"] is None


def test_second_source_coverage_is_listed_not_hidden(tmp_path: Path) -> None:
    session = GuiSession(tmp_path / "index.db")
    session.select_source(EXAMPLE)
    session.import_selected()
    extra = _snapshot(
        tmp_path / "other.json",
        source_id="gui-other",
        events=[{"native_id": "1", "role": "user", "text": "另一来源"}],
    )
    session.select_source(extra)
    session.import_selected()
    ids = [row["id"] for row in session.view()["sources"]]
    assert ids == ["gui-other", "synthetic-demo"]


def test_gui_package_does_not_import_store_or_adapters() -> None:
    import continuum_history.gui as gui
    import continuum_history.gui.bridge as bridge
    import continuum_history.gui.session as session

    for module in (gui, bridge, session):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "HistoryStore" not in source
        assert "load_snapshot" not in source
        assert "load_cursor_state_vscdb" not in source
        assert "continuum_history.store" not in source
        assert "continuum_history.adapters" not in source
