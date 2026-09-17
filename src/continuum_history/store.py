"""One local index shared by CLI, MCP, and the future GUI.

Connections belong to individual operations, not threads or long-lived MCP sessions.
Every paginated query reads its revision and rows in the same SQLite transaction.
"""

import base64
import hashlib
import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from continuum_history.errors import HistoryError
from continuum_history.models import Snapshot

SCHEMA_VERSION = 1
APPLICATION_ID = 0x434E544D  # CNTM: distinguish derived indexes from native databases.
SCHEMA = """
CREATE TABLE meta (revision INTEGER NOT NULL);
INSERT INTO meta VALUES (0);
CREATE TABLE sources (
    id TEXT PRIMARY KEY, digest TEXT NOT NULL, indexed_at TEXT NOT NULL,
    session_count INTEGER NOT NULL, event_count INTEGER NOT NULL
);
CREATE TABLE sessions (
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    native_id TEXT NOT NULL, title TEXT NOT NULL, project TEXT,
    UNIQUE(source_id, native_id)
);
CREATE TABLE events (
    rowid INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    native_id TEXT NOT NULL, ordinal INTEGER NOT NULL, role TEXT NOT NULL,
    text TEXT NOT NULL, search_text TEXT NOT NULL, source_ref TEXT NOT NULL,
    UNIQUE(session_id, native_id), UNIQUE(session_id, ordinal)
);
CREATE INDEX sessions_source ON sessions(source_id);
CREATE INDEX events_session ON events(session_id, ordinal);
CREATE VIRTUAL TABLE search USING fts5(search_text, tokenize='trigram case_sensitive 1');
PRAGMA user_version=1;
PRAGMA application_id=1129206861;
"""


def identity(*parts: str | None) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def page_offset(cursor: str | None, revision: int, query: str) -> int:
    if cursor is None:
        return 0
    try:
        if len(cursor) > 4096:
            raise ValueError
        data = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
        if not isinstance(data, dict) or set(data) != {"v", "r", "q", "o"}:
            raise ValueError
        if data["v"] != 1 or type(data["r"]) is not int or type(data["o"]) is not int:
            raise ValueError
        if not 0 <= data["o"] <= 2**63 - 1 or data["q"] != query:
            raise ValueError
    except (ValueError, TypeError, UnicodeError) as exc:
        raise HistoryError("invalid_cursor: restart with the original query") from exc
    if data["r"] != revision:
        raise HistoryError("stale_cursor: index changed; restart from the first page")
    return int(data["o"])


class HistoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass  # Never silently change permissions on an existing user-selected file.
        else:
            os.close(descriptor)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            app_id = db.execute("PRAGMA application_id").fetchone()[0]
            if version not in (0, SCHEMA_VERSION):
                raise HistoryError("unsupported_schema: use a matching version; never overwrite")
            if (version == SCHEMA_VERSION and app_id != APPLICATION_ID) or (
                version == 0 and app_id
            ):
                raise HistoryError("unsupported_schema: selected file is not a Continuum index")
            if version == 0:
                if db.execute("SELECT name FROM sqlite_master").fetchone():
                    raise HistoryError("unsupported_schema: selected file is not a Continuum index")
                try:
                    for statement in SCHEMA.split(";"):
                        if statement.strip():
                            db.execute(statement)
                except sqlite3.OperationalError as exc:
                    raise HistoryError(
                        "index_init_failed: SQLite with FTS5 trigram is required"
                    ) from exc
            db.commit()
            db.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def replace_source(self, snapshot: Snapshot) -> dict[str, Any]:
        """Atomically replace exactly one explicitly supplied full source snapshot."""
        snapshot = Snapshot.model_validate(snapshot.model_dump())
        digest = hashlib.sha256(snapshot.model_dump_json().encode()).hexdigest()
        event_count = sum(len(session.events) for session in snapshot.sessions)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT digest FROM sources WHERE id=?", (snapshot.source_id,)
            ).fetchone()
            if previous and previous[0] == digest:
                return {"source_id": snapshot.source_id, "changed": False}
            db.execute(
                "DELETE FROM search WHERE rowid IN (SELECT e.rowid FROM events e "
                "JOIN sessions s ON s.id=e.session_id WHERE s.source_id=?)",
                (snapshot.source_id,),
            )
            db.execute("DELETE FROM sources WHERE id=?", (snapshot.source_id,))
            db.execute(
                "INSERT INTO sources VALUES (?, ?, ?, ?, ?)",
                (
                    snapshot.source_id,
                    digest,
                    datetime.now(UTC).isoformat(),
                    len(snapshot.sessions),
                    event_count,
                ),
            )
            for session in snapshot.sessions:
                sid = identity(snapshot.source_id, session.native_id)
                db.execute(
                    "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                    (sid, snapshot.source_id, session.native_id, session.title, session.project),
                )
                for ordinal, event in enumerate(session.events):
                    eid = identity(snapshot.source_id, session.native_id, event.native_id)
                    ref = (
                        f"continuum-snapshot://{snapshot.source_id}/"
                        f"{quote(session.native_id, safe='')}/{quote(event.native_id, safe='')}"
                    )
                    inserted = db.execute(
                        "INSERT INTO events (id, session_id, native_id, ordinal, role, text, "
                        "search_text, source_ref) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            eid,
                            sid,
                            event.native_id,
                            ordinal,
                            event.role,
                            event.text,
                            event.text.casefold(),
                            ref,
                        ),
                    )
                    db.execute(
                        "INSERT INTO search(rowid, search_text) VALUES (?, ?)",
                        (inserted.lastrowid, event.text.casefold()),
                    )
            db.execute("UPDATE meta SET revision=revision+1")
        return {
            "source_id": snapshot.source_id,
            "changed": True,
            "session_count": len(snapshot.sessions),
            "event_count": event_count,
        }

    def sources(self) -> dict[str, Any]:
        with self.connection() as db:
            db.execute("BEGIN")
            revision = db.execute("SELECT revision FROM meta").fetchone()[0]
            items = [
                {
                    **dict(row),
                    "adapter": "continuum-snapshot-v1",
                    "coverage": "supplied_snapshot",
                    "live": False,
                }
                for row in db.execute("SELECT * FROM sources ORDER BY id")
            ]
            return {
                "items": items,
                "index_revision": revision,
                "native_adapters": "not_implemented",
            }

    def _page(
        self,
        db: sqlite3.Connection,
        sql: str,
        params: list[Any],
        *,
        key: str,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise HistoryError("invalid_limit: choose 1 through 100")
        revision = db.execute("SELECT revision FROM meta").fetchone()[0]
        offset = page_offset(cursor, revision, key)
        rows = db.execute(sql + " LIMIT ? OFFSET ?", (*params, limit + 1, offset)).fetchall()
        token = None
        if len(rows) > limit:
            token = base64.urlsafe_b64encode(
                json.dumps({"v": 1, "r": revision, "q": key, "o": offset + limit}).encode()
            ).decode()
        return {
            "items": [dict(row) for row in rows[:limit]],
            "next_cursor": token,
            "index_revision": revision,
        }

    @staticmethod
    def _filters(source_id: str | None, project: str | None) -> tuple[str, list[Any]]:
        clauses, params = [], []
        for column, value in (("s.source_id", source_id), ("s.project", project)):
            if value is not None:
                clauses.append(f" AND {column}=?")
                params.append(value)
        return "".join(clauses), params

    def list_sessions(
        self,
        *,
        source_id: str | None = None,
        project: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        filters, params = self._filters(source_id, project)
        with self.connection() as db:
            db.execute("BEGIN")
            return self._page(
                db,
                "SELECT s.* FROM sessions s WHERE 1=1" + filters + " ORDER BY s.id",
                params,
                key=identity("list", source_id, project),
                limit=limit,
                cursor=cursor,
            )

    def read(
        self, session_id: str, *, limit: int = 20, cursor: str | None = None
    ) -> dict[str, Any]:
        with self.connection() as db:
            db.execute("BEGIN")
            session = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            if session is None:
                raise HistoryError("not_found: session is not in this index")
            result = self._page(
                db,
                "SELECT id, native_id, ordinal, role, text, source_ref FROM events "
                "WHERE session_id=? ORDER BY ordinal",
                [session_id],
                key=identity("read", session_id),
                limit=limit,
                cursor=cursor,
            )
            result["session"] = dict(session)
            return result

    def search(
        self,
        query: str,
        *,
        source_id: str | None = None,
        project: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        if not query.strip() or len(query) > 512 or "\x00" in query:
            raise HistoryError("invalid_query: use 1–512 characters, excluding NUL")
        needle = query.casefold()
        filters, params = self._filters(source_id, project)
        # FTS narrows >=3-character queries; instr enforces literal substring semantics.
        # Short CJK queries still work (a slower scan), instead of silently returning zero.
        fts = ""
        query_params: list[Any] = [needle]
        if len(needle) >= 3:
            fts = " AND e.rowid IN (SELECT rowid FROM search WHERE search MATCH ?)"
            query_params.append('"' + needle.replace('"', '""') + '"')
        sql = (
            "SELECT e.id, e.session_id, e.native_id, e.ordinal, e.role, e.source_ref, "
            "s.source_id, s.title, s.project, "
            "substr(e.text, 1, 240) AS preview, length(e.text)>240 AS preview_truncated "
            "FROM events e JOIN sessions s ON s.id=e.session_id "
            "WHERE instr(e.search_text, ?)>0" + fts + filters + " ORDER BY s.id, e.ordinal"
        )
        with self.connection() as db:
            db.execute("BEGIN")
            return self._page(
                db,
                sql,
                query_params + params,
                key=identity("search", query, source_id, project),
                limit=limit,
                cursor=cursor,
            )
