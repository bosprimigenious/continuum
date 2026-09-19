# Architecture decision 001: local core, multiple clients

Status: accepted for the foundation. GUI transport was validated in P5-a as CLI subprocess JSON.

## Boundaries

`adapters` validate source-format data into `models.Snapshot`. `store.HistoryStore` owns
index transactions and queries. `cli` performs explicit user-initiated imports; `mcp_server`
only queries an index chosen when launching the process. GUI handlers use this same core
through the `continuum` CLI, not their own parsers, database or search logic.

There is one Python distribution, not a service mesh. No Continuum HTTP API or background
daemon is part of the snapshot workflow. The Vite `npm run dev` host may spawn that CLI
for the browser shell; it is not a second search service. New MCP connections may be
separate processes; operation-scoped SQLite connections avoid sharing one connection across
worker threads.

## Stack and rejected alternatives

| Area | Choice | Why / cost |
| --- | --- | --- |
| Runtime | Python >=3.12, uv | Short feedback loop for parsing, SQLite and existing local prototype knowledge; desktop bundling needs investigation |
| Contracts | Pydantic v2 | One validated model for fixtures and imports; extra fields and duplicate identities fail visibly |
| Storage | stdlib SQLite, WAL, FTS5 trigram | Transactional and rebuildable without another service; short queries scan and large-corpus performance is unmeasured |
| Agent interface | Official MCP Python SDK v2, stdio | Delegate protocol/version negotiation; do not hand-roll JSON-RPC or blindly echo versions |
| Human interface | React + TypeScript + Vite over CLI JSON | Search/read UI; `continuum_history.gui.CliBridge` subprocesses `python -m continuum_history`. Browser e2e unverified |
| Desktop shell | Tauri 2 + PyInstaller CLI sidecar | P6-a: unsigned macOS `.app` built locally. Windows NSIS not built here. Do not add Electron |
| Checks | pytest / Ruff / strict mypy / GitHub Actions | One executable aggregate gate instead of manual green checkmarks |

Do not add Rust to the core, an ORM, a vector database, cloud auth or a workflow engine now.
Reconsider SQLite only after a measured workload demonstrates an actual limitation.
If Python sidecar packaging is unreliable on a target platform, record evidence before revisiting
the desktop shell. Do not maintain Tauri and Electron implementations in parallel.

Primary references: [MCP SDK](https://github.com/modelcontextprotocol/python-sdk),
[SQLite FTS5](https://www.sqlite.org/fts5.html), [uv projects](https://docs.astral.sh/uv/guides/projects/).
Dependency versions are resolved in `uv.lock`, not copied from a tutorial.

## Current data contract

`examples/synthetic.snapshot.json` is the executable shape of normalized schema v1:

- Snapshot: `schema_version=1`, a source-instance `source_id`, complete `sessions`.
- Session: source-native `native_id`, title, nullable project, ordered `events`,
  optional `created_at` / `updated_at`.
- Event: source-native `native_id`, role, text, optional `created_at`. Event identities are
  unique within a session.
- Snapshot: `adapter` (default `continuum-snapshot-v1`) and optional structured `coverage`
  for native readers.
- Full source snapshots are bounded to 16 MiB at the file reader; individual text to 1,000,000
  characters. NUL is rejected explicitly because SQLite text functions treat it inconsistently.
- Native Cursor `state.vscdb` imports are not bounded by the snapshot file cap; they copy
  the selected main file plus WAL/SHM sidecars to a temporary directory, then query
  `cursorDiskKV` with `mode=ro`. Direct SQLite WAL readers update the source SHM; the copy
  keeps that write off the vendor files. Unsupported tool/thinking/media fields become
  coverage issues instead of being concatenated into `text`.
- These are foundation constraints, not claims about native log limits. Branches, media
  blocks and JSONL Cursor transcripts remain unimplemented.

Stable IDs hash the tuple `(source instance, native session[, native event])`, never text alone.
Source references use an encoded `continuum-snapshot://` namespace and are not arbitrary file paths.
The source digest and global index revision identify the imported content version. References
identify events in the current snapshot; no historical version archive is kept.

An import validates everything before a write transaction. Blocking native coverage
(`unknown_shape`, `illegal_identity`, `malformed_record`, `missing_bubble`, `duplicate_event`,
`invalid_composer`) raises `incomplete_source` and does not replace the previous index.
Unsupported tool/thinking blocks and extra `bubbleId` rows not listed in headers
(`orphaned_bubble`) are not blocking. Unchanged canonical snapshots are no-ops.
Any database failure rolls back the replacement. A failed import leaves the previous successful
snapshot; the CLI exits nonzero, does not create a new empty `--db` for a blocked native import,
and does not claim a new successful indexing time.

Only an empty unclaimed SQLite file or an existing index with the Continuum application ID and
supported schema is accepted. Future schemas fail closed. New POSIX index files are created
with owner-only permissions. Existing permissions are not silently changed; Windows ACLs need
user/installer policy. This does not defend against another process running as the same user.

## Query contract

- Literal, casefolded Unicode substring search; no query language or semantic ranking.
- FTS5 trigram narrows queries of >=3 code points; `instr` checks literal matches. Short queries
  use a scan. `%`, `_` and quotes are literal, not SQL wildcards or operators.
- Exact source/project filters are applied before pagination. They are not security ACLs.
- Results have deterministic identity order (not recency order, which needs native timestamps).
- Search returns the first 240 text characters as a **preview**, not a centered match snippet;
  `preview_truncated` explicitly marks shortening. Read returns complete event text.
- Page size is 1–100 events/sessions. Cursors bind operation, exact filters and global revision.
  The revision and rows are read in one SQLite transaction. A changed index returns `stale_cursor`;
  restart paging. An unchanged reimport preserves cursors. Cursors are not authentication tokens.
- MCP translates safe domain errors into SDK `ToolError` so recovery codes reach the client.

The current MCP server exposes the whole selected index. Per-project authorization must be
implemented in the shared service before supporting different permissions inside one index.
Do not describe the current exact filters as authorization.

## GUI bridge (P5-a)

Validated transport: subprocess to the existing CLI. The child argv is
`python -m continuum_history --db INDEX COMMAND...` (the same interface as the `continuum`
console script). Success is JSON on stdout; domain failures are JSON `{"error": ...}` on
stderr with exit 2. `continuum_history.gui` must not import `store` or `adapters`.
Allowed GUI commands are `import`, `sources`, `list`, `search`, and `read` — never `serve`.
The Vite `/__continuum` POST endpoint exists only while `npm run dev` is running and spawns
that same CLI; Continuum does not ship an HTTP search server. Empty UI state must not create
an index or walk the home directory. Tauri P6-a uses the same CLI as a sidecar, not this Vite middleware.

## Migration and deletion

No vendor database writes, source deletion, automatic cleanup or side-bar imports.
The importer reads a stable explicitly supplied normalized snapshot; it does not watch files.
Old migration archives can become a separate adapter later, with visible archived identity.

Pre-alpha index schema changes must be documented. There is no automatic migration today:
stop clients, retain the old index as a rollback copy, create a **new** path, reimport retained
snapshots and verify counts/search before pointing clients to the new index. Do not overwrite
the only copy. Deleting a row or index is not guaranteed to securely erase WAL/backups/storage.

Current derived index `user_version` is **2** (adapter name, coverage JSON, timestamps).
A v1 foundation index is `unsupported_schema`; do not ALTER it in place. Keep that file,
create a new path, reimport, then retarget CLI/MCP `--db`.

## Deliberately deferred

Native source discovery, live Cursor/host verification, agent-transcripts JSONL, Claude Code
and Codex readers, content-block and media coverage, GUI browser e2e, signed desktop
distribution, task continuity and managed execution. The source adapter and consumer
compatibility matrices are independent. A working MCP client does not prove that client's
native history format can be read on a live host. A green GUI pytest suite does not prove
the Vite shell in a browser. A local unsigned `.app` does not prove a clean-machine install.

CLI packaging is a pure-Python wheel (`continuum-history` on PyPI when published;
console script `continuum`). GitHub Releases may carry that wheel before PyPI exists.
Preferred upload is GitHub OIDC Trusted Publishing, not a long-lived API token in the
repository. Desktop `.app` / `.exe` are P6 packaging artifacts, not the wheel. The PyPI
project name `continuum` is taken by an unrelated package; do not reuse it.
