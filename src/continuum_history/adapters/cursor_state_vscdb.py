"""Read-only Cursor IDE globalStorage state.vscdb adapter.

Supported shape: ``cursorDiskKV`` keys ``composerData:{id}`` and
``bubbleId:{composerId}:{bubbleId}`` with user/assistant ``text`` and optional
timestamps. Tool, thinking, media, JSONL transcripts and workspace DBs are
omitted with coverage issues — they are not stuffed into ``Event.text``.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from continuum_history.errors import HistoryError
from continuum_history.models import CoverageIssue, Event, Session, Snapshot, SnapshotCoverage

ADAPTER: Literal["cursor-state-vscdb-v1"] = "cursor-state-vscdb-v1"
FORMAT: Literal["cursor.global_state.vscdb.cursorDiskKV"] = "cursor.global_state.vscdb.cursorDiskKV"
IssueCode = Literal[
    "malformed_record",
    "missing_bubble",
    "duplicate_event",
    "unsupported_block",
    "unsupported_bubble_type",
    "invalid_composer",
    "unknown_shape",
    "unusable_timestamp",
    "illegal_identity",
    "unrecognized_version",
]
# Versions seen in the locked synthetic fixture, not a vendor compatibility matrix.
KNOWN_COMPOSER_VERSIONS = frozenset({13})
KNOWN_BUBBLE_VERSIONS = frozenset({3})
_ROLES: dict[int, Literal["user", "assistant"]] = {1: "user", 2: "assistant"}
_UNSUPPORTED_FIELDS = ("toolResults", "allThinkingBlocks", "codeBlocks")


def _fingerprint(path: Path) -> tuple[object, ...]:
    parts: list[object] = []
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        try:
            stat = candidate.stat()
        except FileNotFoundError:
            parts.append(None)
            continue
        parts.append((stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
    return tuple(parts)


@contextmanager
def connect_readonly(path: Path) -> Iterator[sqlite3.Connection]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise HistoryError("invalid_cursor_source: not a readable Cursor state database")
    db = sqlite3.connect(resolved.as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        db.execute("PRAGMA query_only=ON")
        db.row_factory = sqlite3.Row
        yield db
    finally:
        db.close()


@contextmanager
def _with_stable_copy(path: Path) -> Iterator[Path]:
    """Copy main+WAL+SHM so SQLite wal-index updates cannot touch the source."""
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise HistoryError("invalid_cursor_source: not a readable Cursor state database")
    with tempfile.TemporaryDirectory(prefix="continuum-cursor-") as tmp:
        dest = Path(tmp) / resolved.name
        shutil.copyfile(resolved, dest)
        for suffix in ("-wal", "-shm"):
            extra = Path(f"{resolved}{suffix}")
            if extra.is_file():
                shutil.copyfile(extra, Path(f"{dest}{suffix}"))
        yield dest


def _ref(value: object) -> str | None:
    if isinstance(value, str) and 1 <= len(value) <= 256 and "\x00" not in value:
        return value
    return None


def _legal_native_id(value: object) -> bool:
    return _ref(value) is not None


def _timestamp(
    value: object,
    issues: list[CoverageIssue],
    session_id: str | None = None,
    event_id: str | None = None,
) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        seconds = value / 1000 if value > 10_000_000_000 else float(value)
        try:
            return datetime.fromtimestamp(seconds, UTC).isoformat()
        except (OverflowError, OSError, ValueError):
            issues.append(_issue("unusable_timestamp", session_id, event_id))
            return None
    if isinstance(value, str) and value and "\x00" not in value and len(value) <= 64:
        return value
    issues.append(_issue("unusable_timestamp", session_id, event_id))
    return None


def _object(raw: object) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _issue(
    code: IssueCode,
    session_id: str | None = None,
    event_id: str | None = None,
) -> CoverageIssue:
    return CoverageIssue(
        code=code, native_session_id=_ref(session_id), native_event_id=_ref(event_id)
    )


def _parse_bubble(
    db: sqlite3.Connection,
    composer_id: str,
    header: object,
    seen_ids: set[str],
    issues: list[CoverageIssue],
    bubble_versions: list[int],
) -> Event | None:
    if not isinstance(header, dict):
        issues.append(_issue("malformed_record", composer_id))
        return None
    bubble_id = header.get("bubbleId")
    if not isinstance(bubble_id, str) or not bubble_id:
        issues.append(_issue("malformed_record", composer_id))
        return None
    if not _legal_native_id(bubble_id):
        issues.append(_issue("illegal_identity", composer_id, bubble_id))
        return None
    if bubble_id in seen_ids:
        issues.append(_issue("duplicate_event", composer_id, bubble_id))
        return None
    row = db.execute(
        "SELECT value FROM cursorDiskKV WHERE key=?",
        (f"bubbleId:{composer_id}:{bubble_id}",),
    ).fetchone()
    if row is None:
        issues.append(_issue("missing_bubble", composer_id, bubble_id))
        return None
    bubble = _object(row[0])
    if bubble is None:
        issues.append(_issue("malformed_record", composer_id, bubble_id))
        return None
    version = bubble.get("_v")
    if isinstance(version, int) and not isinstance(version, bool):
        bubble_versions.append(version)
        if version not in KNOWN_BUBBLE_VERSIONS:
            issues.append(_issue("unrecognized_version", composer_id, bubble_id))
    type_ = bubble.get("type", header.get("type"))
    role = _ROLES.get(type_) if isinstance(type_, int) and not isinstance(type_, bool) else None
    if role is None:
        issues.append(_issue("unsupported_bubble_type", composer_id, bubble_id))
        return None
    for field in _UNSUPPORTED_FIELDS:
        value = bubble.get(field)
        if value:
            issues.append(_issue("unsupported_block", composer_id, bubble_id))
    text = bubble.get("text", "")
    if text is None:
        text = ""
    if not isinstance(text, str):
        issues.append(_issue("malformed_record", composer_id, bubble_id))
        return None
    try:
        event = Event(
            native_id=bubble_id,
            role=role,
            text=text,
            created_at=_timestamp(bubble.get("createdAt"), issues, composer_id, bubble_id),
        )
    except ValidationError:
        issues.append(_issue("malformed_record", composer_id, bubble_id))
        return None
    seen_ids.add(bubble_id)
    return event


def _parse_composer(
    db: sqlite3.Connection,
    key: str,
    raw: object,
    issues: list[CoverageIssue],
    composer_versions: list[int],
    bubble_versions: list[int],
) -> Session | None:
    composer_id = key.split(":", 1)[1]
    if not composer_id:
        issues.append(_issue("malformed_record"))
        return None
    if not _legal_native_id(composer_id):
        issues.append(_issue("illegal_identity", composer_id))
        return None
    data = _object(raw)
    if data is None:
        issues.append(_issue("malformed_record", composer_id))
        return None
    version = data.get("_v")
    if isinstance(version, int) and not isinstance(version, bool):
        composer_versions.append(version)
        if version not in KNOWN_COMPOSER_VERSIONS:
            issues.append(_issue("unrecognized_version", composer_id))
    if "fullConversationHeadersOnly" not in data:
        issues.append(_issue("unknown_shape", composer_id))
        return None
    headers = data["fullConversationHeadersOnly"]
    if not isinstance(headers, list):
        issues.append(
            _issue("unknown_shape" if headers is None else "invalid_composer", composer_id)
        )
        return None
    events: list[Event] = []
    seen: set[str] = set()
    for header in headers:
        event = _parse_bubble(db, composer_id, header, seen, issues, bubble_versions)
        if event is not None:
            events.append(event)
    worktree = data.get("gitWorktree")
    project = None
    if isinstance(worktree, dict):
        path = worktree.get("worktreePath")
        project = path if isinstance(path, str) else None
    title = data.get("name", "")
    if title is None:
        title = ""
    if not isinstance(title, str):
        issues.append(_issue("invalid_composer", composer_id))
        return None
    try:
        return Session(
            native_id=composer_id,
            title=title,
            project=project,
            events=tuple(events),
            created_at=_timestamp(data.get("createdAt"), issues, composer_id),
            updated_at=_timestamp(data.get("lastUpdatedAt"), issues, composer_id),
        )
    except ValidationError:
        issues.append(_issue("invalid_composer", composer_id))
        return None


def load_cursor_state_vscdb(path: Path, *, source_id: str) -> Snapshot:
    """Read one explicitly selected Cursor state.vscdb without modifying it."""
    source = path.expanduser()
    before = _fingerprint(source)
    sessions: list[Session] = []
    issues: list[CoverageIssue] = []
    composer_versions: list[int] = []
    bubble_versions: list[int] = []
    sessions_seen = 0
    events_seen = 0
    try:
        with _with_stable_copy(source) as readable, connect_readonly(readable) as db:
            tables = {
                row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "cursorDiskKV" not in tables:
                raise HistoryError(
                    "invalid_cursor_source: expected cursorDiskKV table in a Cursor state.vscdb"
                )
            rows = db.execute(
                "SELECT key, value FROM cursorDiskKV WHERE key LIKE 'composerData:%' ORDER BY key"
            ).fetchall()
            for key, value in rows:
                sessions_seen += 1
                parsed = _object(value)
                headers = parsed.get("fullConversationHeadersOnly") if parsed else None
                if isinstance(headers, list):
                    events_seen += len(headers)
                session = _parse_composer(
                    db, key, value, issues, composer_versions, bubble_versions
                )
                if session is not None:
                    sessions.append(session)
    except HistoryError:
        raise
    except sqlite3.Error as exc:
        raise HistoryError("invalid_cursor_source: not a readable Cursor state database") from exc
    if before != _fingerprint(source):
        raise HistoryError("source_changed: retry with a stable snapshot")
    imported_events = sum(len(session.events) for session in sessions)
    coverage = SnapshotCoverage(
        adapter=ADAPTER,
        format=FORMAT,
        observed_composer_data_version=max(composer_versions) if composer_versions else None,
        observed_bubble_version=max(bubble_versions) if bubble_versions else None,
        sessions_seen=sessions_seen,
        sessions_imported=len(sessions),
        events_seen=events_seen,
        events_imported=imported_events,
        issues=tuple(issues),
        complete=not issues and sessions_seen == len(sessions) and events_seen == imported_events,
    )
    try:
        return Snapshot(
            schema_version=1,
            source_id=source_id,
            adapter=ADAPTER,
            sessions=tuple(sessions),
            coverage=coverage,
        )
    except ValidationError as exc:
        raise HistoryError("invalid_cursor_source: native records did not fit schema v1") from exc
