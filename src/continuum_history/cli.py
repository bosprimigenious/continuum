"""Explicit local index selection; importing is a CLI-only user action."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from continuum_history.adapters.cursor_state_vscdb import load_cursor_state_vscdb
from continuum_history.adapters.snapshot import load_snapshot
from continuum_history.errors import HistoryError
from continuum_history.models import Snapshot
from continuum_history.store import HistoryStore

_COMMANDS = frozenset({"import", "sources", "list", "search", "read", "serve"})
_VALUE_FLAGS = frozenset(
    {
        "--db",
        "--limit",
        "--cursor",
        "--source",
        "--project",
        "--adapter",
        "--source-id",
        "--format",
    }
)


def _load_import(path: Path, adapter: str, source_id: str | None) -> Snapshot:
    if adapter == "snapshot":
        return load_snapshot(path)
    if not source_id:
        raise HistoryError("invalid_import: --source-id is required for cursor-state-vscdb")
    return load_cursor_state_vscdb(path, source_id=source_id)


def _with_implicit_search(argv: list[str]) -> list[str]:
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in _COMMANDS:
            return argv
        if arg in _VALUE_FLAGS:
            index += 2
            continue
        if arg.startswith("--") and "=" in arg:
            index += 1
            continue
        if arg.startswith("-"):
            index += 1
            continue
        return argv[:index] + ["search"] + argv[index:]
    return argv


def _resolve_db(requested: Path | None) -> Path:
    if requested is not None:
        return requested
    env = os.environ.get("CONTINUUM_DB", "").strip()
    if env:
        return Path(env)
    raise HistoryError("invalid_import: explicit db path required (--db or CONTINUUM_DB)")


def _configure_stdio() -> None:
    # Frozen Windows sidecars ignore PYTHONUTF8/PYTHONIOENCODING and keep cp1252.
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError, AttributeError):
            continue


def _want_text(fmt: str) -> bool:
    if fmt == "text":
        return True
    if fmt == "json":
        return False
    return sys.stdout.isatty()


def _render_text(command: str, result: dict[str, Any]) -> str:
    if command == "import":
        return (
            f"imported source_id={result.get('source_id')} changed={result.get('changed')} "
            f"sessions={result.get('session_count')} events={result.get('event_count')}"
        )
    items = list(result.get("items") or [])
    if command == "search":
        if not items:
            return "no matches"
        blocks = []
        for item in items:
            title = str(item.get("title") or item.get("session_id") or "")
            preview = str(item.get("preview") or "")
            session_id = str(item.get("session_id") or item.get("id") or "")
            lines = [title]
            if preview:
                lines.append(f"  {preview}")
            lines.append(f"  {session_id}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)
    if command == "list":
        if not items:
            return "no sessions"
        return "\n".join(
            f"{item.get('title') or item.get('id')}\n  {item.get('id')}" for item in items
        )
    if command == "read":
        if not items:
            return "no events"
        return "\n\n".join(
            f"{item.get('role')}\n{item.get('text')}"
            for item in items
            if item.get("text") is not None
        )
    if command == "sources":
        if not items:
            return "no sources"
        lines = []
        for item in items:
            coverage = item.get("coverage") if isinstance(item.get("coverage"), dict) else {}
            status = coverage.get("status") if isinstance(coverage, dict) else None
            lines.append(f"{item.get('id')}  {item.get('adapter')}  {status or ''}".rstrip())
        return "\n".join(lines)
    return json.dumps(result, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(
        prog="continuum",
        description="Local history index (pre-alpha). Query like: continuum search 数据库锁",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Dedicated derived SQLite index (or CONTINUUM_DB)",
    )
    parser.add_argument(
        "--format",
        choices=("auto", "json", "text"),
        default="auto",
        help="auto: JSON when piped, text in a terminal",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser(
        "import",
        help="Import a normalized v1 snapshot or one explicitly selected native source",
    )
    ingest.add_argument("file", type=Path)
    ingest.add_argument(
        "--adapter",
        choices=("snapshot", "cursor-state-vscdb"),
        default="snapshot",
        help="snapshot (default) or cursor-state-vscdb",
    )
    ingest.add_argument(
        "--source-id",
        help="Required identity for native adapters; ignored for snapshot files",
    )
    sub.add_parser("sources", help="Show explicitly imported snapshot coverage")
    for name in ("list", "search", "read"):
        command = sub.add_parser(name)
        command.add_argument("--limit", type=int, default=20)
        command.add_argument("--cursor")
        if name in ("list", "search"):
            command.add_argument("--source", dest="source_id")
            command.add_argument("--project")
        if name == "search":
            command.add_argument("query")
        if name == "read":
            command.add_argument("session_id")
    sub.add_parser("serve", help="Expose this entire index through read-only MCP over stdio")
    args = parser.parse_args(_with_implicit_search(sys.argv[1:] if argv is None else argv))
    try:
        snapshot = None
        if args.command == "import":
            snapshot = _load_import(args.file, args.adapter, args.source_id)
            HistoryStore.reject_blocking_coverage(snapshot)
        store = HistoryStore(_resolve_db(args.db))
        match args.command:
            case "import":
                assert snapshot is not None
                result = store.replace_source(snapshot)
            case "sources":
                result = store.sources()
            case "list" | "search":
                kwargs = {
                    "source_id": args.source_id,
                    "project": args.project,
                    "limit": args.limit,
                    "cursor": args.cursor,
                }
                result = (
                    store.search(args.query, **kwargs)
                    if args.command == "search"
                    else store.list_sessions(**kwargs)
                )
            case "read":
                result = store.read(args.session_id, limit=args.limit, cursor=args.cursor)
            case "serve":
                from continuum_history.mcp_server import create_server

                create_server(store).run(transport="stdio")
                return 0
            case _:
                raise AssertionError("unreachable argparse command")
        if _want_text(args.format):
            print(_render_text(args.command, result))
        else:
            print(json.dumps(result, ensure_ascii=True))
        return 0
    except (HistoryError, OSError, sqlite3.Error) as exc:
        message = str(exc) if isinstance(exc, HistoryError) else type(exc).__name__
        print(json.dumps({"error": message}), file=sys.stderr)
        return 2
