"""GUI workflow: explicit source → import → coverage → search → paged read → refresh."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from continuum_history.errors import HistoryError
from continuum_history.gui.bridge import CliBridge

ViewState = Literal["empty", "ready", "error"]


class GuiSession:
    def __init__(self, index: Path) -> None:
        self.index = index
        self._bridge = CliBridge(index)
        self._source: Path | None = None
        self._adapter = "snapshot"
        self._source_id: str | None = None
        self._error: str | None = None
        self._imported = False
        self._sources: list[dict[str, Any]] = []
        self._items: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []
        self._next_cursor: str | None = None
        self._next_read_cursor: str | None = None

    def view(self) -> dict[str, Any]:
        if self._error is not None:
            state: ViewState = "error"
        elif self._imported:
            state = "ready"
        else:
            state = "empty"
        return {
            "state": state,
            "sources": list(self._sources),
            "items": list(self._items),
            "events": list(self._events),
            "next_cursor": self._next_cursor,
            "next_read_cursor": self._next_read_cursor,
            "error": self._error,
        }

    def select_source(
        self,
        path: Path,
        *,
        adapter: str = "snapshot",
        source_id: str | None = None,
    ) -> None:
        self._source = path
        self._adapter = adapter
        self._source_id = source_id

    def import_selected(self) -> dict[str, Any]:
        if self._source is None:
            error = "invalid_import: no source selected"
            self._error = error
            raise HistoryError(error)
        command = ["import", str(self._source), "--adapter", self._adapter]
        if self._source_id is not None:
            command.extend(["--source-id", self._source_id])
        return self._call(self._after_import, *command)

    def refresh(self) -> dict[str, Any]:
        return self.import_selected()

    def list_sessions(self, *, limit: int = 20, cursor: str | None = None) -> dict[str, Any]:
        if not self._imported:
            return {"items": [], "next_cursor": None, "index_revision": 0}
        command = ["list", "--limit", str(limit)]
        if cursor is not None:
            command.extend(["--cursor", cursor])

        def after(payload: dict[str, Any]) -> None:
            self._set_items(payload, append=cursor is not None)

        return self._call(after, *command)

    def search(self, query: str, *, limit: int = 20, cursor: str | None = None) -> dict[str, Any]:
        if not self._imported:
            return {"items": [], "next_cursor": None, "index_revision": 0}
        command = ["search", query, "--limit", str(limit)]
        if cursor is not None:
            command.extend(["--cursor", cursor])

        def after(payload: dict[str, Any]) -> None:
            self._set_items(payload, append=cursor is not None)

        return self._call(after, *command)

    def read(
        self, session_id: str, *, limit: int = 20, cursor: str | None = None
    ) -> dict[str, Any]:
        command = ["read", session_id, "--limit", str(limit)]
        if cursor is not None:
            command.extend(["--cursor", cursor])

        def after(payload: dict[str, Any]) -> None:
            self._set_events(payload, append=cursor is not None)

        return self._call(after, *command)

    def _call(
        self, after: Callable[[dict[str, Any]], None] | None, *command: str
    ) -> dict[str, Any]:
        try:
            payload = self._bridge.run(*command)
        except HistoryError as exc:
            self._error = str(exc)
            raise
        self._error = None
        if after is not None:
            after(payload)
        return payload

    def _after_import(self, _payload: dict[str, Any]) -> None:
        self._imported = True
        self._sources = list(self._bridge.run("sources").get("items") or [])
        self._items = []
        self._events = []
        self._next_cursor = None
        self._next_read_cursor = None

    def _set_items(self, payload: dict[str, Any], *, append: bool) -> None:
        page = list(payload.get("items") or [])
        self._items = [*self._items, *page] if append else page
        next_cursor = payload.get("next_cursor")
        self._next_cursor = next_cursor if isinstance(next_cursor, str) else None

    def _set_events(self, payload: dict[str, Any], *, append: bool) -> None:
        page = list(payload.get("items") or [])
        self._events = [*self._events, *page] if append else page
        next_cursor = payload.get("next_cursor")
        self._next_read_cursor = next_cursor if isinstance(next_cursor, str) else None
