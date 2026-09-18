"""Build synthetic Cursor IDE globalStorage state.vscdb fixtures.

Format contract (one observed shape, not a vendor specification):

- File: SQLite database named like Cursor ``state.vscdb``.
- Tables used: ``cursorDiskKV(key TEXT PRIMARY KEY, value TEXT)``.
- Session document: key ``composerData:{composerId}``, JSON with ``_v``,
  ``composerId``, ``name``, ``createdAt`` (unix ms), ``lastUpdatedAt``,
  ``fullConversationHeadersOnly`` (ordered ``bubbleId`` + ``type``),
  optional ``gitWorktree.worktreePath``.
- Message document: key ``bubbleId:{composerId}:{bubbleId}``, JSON with
  ``_v``, ``type`` (1=user, 2=assistant), optional ``text``, optional
  ``createdAt`` (unix ms or ISO string).
- Observed from public reverse-engineering of Cursor IDE 2.4–3.17 (2026),
  macOS/Linux/Windows path variants. This helper never reads a live host.

Out of scope for this fixture (must not be claimed as supported):

- ``~/.cursor/projects/*/agent-transcripts`` JSONL
- workspaceStorage sidebar DBs and ``composer.composerHeaders``
- ``checkpointId``, ``messageRequestContext``, ``agentKv``, protobuf blobs
- tool / thinking / media blocks (present only as unsupported coverage)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

COMPOSER_A = "00000000-0000-4000-8000-0000000000aa"
BUBBLE_USER = "00000000-0000-4000-8000-0000000000b1"
BUBBLE_ASSISTANT = "00000000-0000-4000-8000-0000000000b2"
BUBBLE_TOOLISH = "00000000-0000-4000-8000-0000000000b3"
KNOWN_USER_TEXT = "How do we investigate a SQLite 数据库锁 in Cursor?"
KNOWN_ASSISTANT_TEXT = "Inspect WAL mode. This is synthetic fixture text, not a real chat."
PRIVATE_SENTINEL = "PRIVATE_SENTINEL_MUST_NOT_LEAK"
SYNTHETIC_PROJECT = "/workspace/demo-project"


def _connect(path: Path, *, wal: bool) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    if wal:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA wal_autocheckpoint=0")
    db.execute("CREATE TABLE IF NOT EXISTS ItemTable (key TEXT PRIMARY KEY, value TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS cursorDiskKV (key TEXT PRIMARY KEY, value TEXT)")
    return db


def put_kv(db: sqlite3.Connection, key: str, value: str | dict[str, Any]) -> None:
    payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    db.execute("INSERT OR REPLACE INTO cursorDiskKV(key, value) VALUES (?, ?)", (key, payload))


def composer_payload(
    composer_id: str,
    headers: list[dict[str, Any]],
    *,
    name: str | None = "Synthetic Cursor database discussion",
    created_at: int | None = 1_737_316_260_000,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "_v": 13,
        "composerId": composer_id,
        "fullConversationHeadersOnly": headers,
        "unifiedMode": "agent",
        "gitWorktree": {"worktreePath": SYNTHETIC_PROJECT, "branchName": "main"},
    }
    if name is not None:
        payload["name"] = name
    if created_at is not None:
        payload["createdAt"] = created_at
        payload["lastUpdatedAt"] = created_at + 5_000
    if extra:
        payload.update(extra)
    return payload


def bubble_payload(
    type_: int,
    text: str | None,
    *,
    created_at: int | str | None = 1_737_316_260_000,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"_v": 3, "type": type_}
    if text is not None:
        payload["text"] = text
    if created_at is not None:
        payload["createdAt"] = created_at
    if extra:
        payload.update(extra)
    return payload


def write_state_vscdb(
    path: Path,
    *,
    wal: bool = False,
    composers: list[tuple[str, dict[str, Any] | str]] | None = None,
    bubbles: list[tuple[str, str, dict[str, Any] | str]] | None = None,
    item_table: dict[str, Any] | None = None,
) -> sqlite3.Connection:
    """Write a synthetic vscdb and return the still-open connection (caller closes)."""
    db = _connect(path, wal=wal)
    db.execute(
        "INSERT OR REPLACE INTO ItemTable(key, value) VALUES (?, ?)",
        ("workbench.panel.aichat.view.aichat.chatdata", json.dumps({"secret": PRIVATE_SENTINEL})),
    )
    put_kv(db, f"checkpointId:{COMPOSER_A}:ignored", {"diff": PRIVATE_SENTINEL})
    if item_table:
        for key, value in item_table.items():
            db.execute(
                "INSERT OR REPLACE INTO ItemTable(key, value) VALUES (?, ?)",
                (key, json.dumps(value) if not isinstance(value, str) else value),
            )
    for composer_id, payload in composers or []:
        put_kv(db, f"composerData:{composer_id}", payload)
    for composer_id, bubble_id, payload in bubbles or []:
        put_kv(db, f"bubbleId:{composer_id}:{bubble_id}", payload)
    db.commit()
    return db


def supported_conversation(path: Path, *, wal: bool = False) -> sqlite3.Connection:
    headers = [
        {"bubbleId": BUBBLE_USER, "type": 1},
        {"bubbleId": BUBBLE_ASSISTANT, "type": 2},
        {"bubbleId": BUBBLE_TOOLISH, "type": 2},
    ]
    return write_state_vscdb(
        path,
        wal=wal,
        composers=[(COMPOSER_A, composer_payload(COMPOSER_A, headers))],
        bubbles=[
            (COMPOSER_A, BUBBLE_USER, bubble_payload(1, KNOWN_USER_TEXT)),
            (COMPOSER_A, BUBBLE_ASSISTANT, bubble_payload(2, KNOWN_ASSISTANT_TEXT)),
            (
                COMPOSER_A,
                BUBBLE_TOOLISH,
                bubble_payload(
                    2,
                    "",
                    extra={
                        "toolResults": [{"name": "shell", "body": PRIVATE_SENTINEL}],
                        "allThinkingBlocks": [{"text": PRIVATE_SENTINEL}],
                    },
                ),
            ),
        ],
    )


def long_conversation(path: Path, count: int = 40) -> None:
    headers = [
        {"bubbleId": f"bubble-{i:04d}", "type": 1 if i % 2 == 0 else 2} for i in range(count)
    ]
    bubbles = [
        (
            COMPOSER_A,
            f"bubble-{i:04d}",
            bubble_payload(
                1 if i % 2 == 0 else 2,
                ("How do we investigate a SQLite 数据库锁? " if i == 0 else "")
                + f"turn-{i:04d} marker={'end-marker' if i == count - 1 else i}",
            ),
        )
        for i in range(count)
    ]
    write_state_vscdb(
        path,
        composers=[
            (
                COMPOSER_A,
                composer_payload(COMPOSER_A, headers, name="Long synthetic Cursor session"),
            )
        ],
        bubbles=bubbles,
    ).close()
