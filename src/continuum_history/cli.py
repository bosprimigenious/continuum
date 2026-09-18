"""Explicit local index selection; importing is a CLI-only user action."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from continuum_history.adapters.cursor_state_vscdb import load_cursor_state_vscdb
from continuum_history.adapters.snapshot import load_snapshot
from continuum_history.errors import HistoryError
from continuum_history.models import Snapshot
from continuum_history.store import HistoryStore


def _load_import(path: Path, adapter: str, source_id: str | None) -> Snapshot:
    if adapter == "snapshot":
        return load_snapshot(path)
    if not source_id:
        raise HistoryError("invalid_import: --source-id is required for cursor-state-vscdb")
    return load_cursor_state_vscdb(path, source_id=source_id)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="continuum", description="Local history index (pre-alpha)"
    )
    parser.add_argument("--db", type=Path, required=True, help="Dedicated derived SQLite index")
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
    args = parser.parse_args()
    try:
        # Validate input before even creating the derived database.
        snapshot = None
        if args.command == "import":
            snapshot = _load_import(args.file, args.adapter, args.source_id)
            HistoryStore.reject_blocking_coverage(snapshot)
        store = HistoryStore(args.db)
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
        # Machine-readable JSON must survive non-UTF-8 redirected Windows/legacy terminals.
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except (HistoryError, OSError, sqlite3.Error) as exc:
        # Do not include a user's paths or database error values in default output.
        message = str(exc) if isinstance(exc, HistoryError) else type(exc).__name__
        print(json.dumps({"error": message}), file=sys.stderr)
        return 2
