"""GUI workflow: explicit source → import → coverage → search → paged read → refresh."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from continuum_history.errors import HistoryError
from continuum_history.gui.bridge import CliBridge

ViewState = Literal["empty", "ready", "error"]
WORKBENCH_PANES = ("navigator", "transcript", "coverage", "settings")


class GuiSession:
    def __init__(self, index: Path) -> None:
        self.index = index
        self._bridge = CliBridge(index)
        self._source: Path | None = None
        self._adapter = "snapshot"
        self._source_id: str | None = None
        self._error: str | None = None
        self._imported = False
        self._proxy: str | None = None
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
            "panes": list(WORKBENCH_PANES),
            "sources": list(self._sources),
            "items": list(self._items),
            "events": list(self._events),
            "next_cursor": self._next_cursor,
            "next_read_cursor": self._next_read_cursor,
            "error": self._error,
            "settings": {"index": str(self.index), "proxy": self._proxy},
        }

    def set_proxy(self, proxy: str | None) -> None:
        self._proxy = proxy.strip() if proxy and proxy.strip() else None

    def save_settings(self, config_dir: Path) -> Path:
        config_dir.mkdir(parents=True, exist_ok=True)
        path = config_dir / "settings.json"
        path.write_text(
            json.dumps({"proxy": self._proxy, "index": str(self.index)}, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def load_settings(self, config_dir: Path) -> dict[str, Any]:
        path = config_dir / "settings.json"
        if not path.is_file():
            return {"proxy": None, "index": str(self.index)}
        payload = json.loads(path.read_text(encoding="utf-8"))
        proxy = payload.get("proxy")
        self.set_proxy(proxy if isinstance(proxy, str) else None)
        return {"proxy": self._proxy, "index": str(self.index)}

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
            payload = self._bridge.run(*command, extra_env=self._proxy_env())
        except HistoryError as exc:
            self._error = str(exc)
            raise
        self._error = None
        if after is not None:
            after(payload)
        return payload

    def _after_import(self, _payload: dict[str, Any]) -> None:
        self._imported = True
        self._sources = list(
            self._bridge.run("sources", extra_env=self._proxy_env()).get("items") or []
        )
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

    def _proxy_env(self) -> dict[str, str] | None:
        if self._proxy is None:
            return None
        return {
            "HTTPS_PROXY": self._proxy,
            "https_proxy": self._proxy,
            "HTTP_PROXY": self._proxy,
            "http_proxy": self._proxy,
        }
