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
| Desktop shell | Tauri 2 + PyInstaller CLI sidecar | P6-a: unsigned macOS `.app` built locally. Windows NSIS produced on GitHub `windows-latest` (start/query not run). Do not add Electron |
| Checks | pytest / Ruff / strict mypy / GitHub Actions | One executable aggregate gate instead of manual green checkmarks |

Do not add Rust to the core, an ORM, a vector database, cloud auth or a workflow engine now.
Reconsider SQLite only after a measured workload demonstrates an actual limitation.
If Python sidecar packaging is unreliable on a target platform, record evidence before revisiting
the desktop shell. Do not maintain Tauri and Electron implementations in parallel.

Primary references: [MCP SDK](https://github.com/modelcontextprotocol/python-sdk),
[SQLite FTS5](https://www.sqlite.org/fts5.html), [uv projects](https://docs.astral.sh/uv/guides/projects/).
Dependency versions are resolved in `uv.lock`, not copied from a tutorial.

## Architecture decision 002: one core, multiple shells

Status: accepted 2026-09-20.

Continuum is a **local conversation-history index**, not a coding agent that edits
repositories. How it ships still follows Grok / Codex (one runtime, many shells), not
Cursor (VS Code fork + editor). The language inside the core stays Python (decision 001).

### Which product line this is

| Route | What it is | When Continuum uses it |
| --- | --- | --- |
| Core + CLI + thin desktop | One library does import/search/read; GUI is a window on that CLI | **Now** |
| Editor extension | Same core; the editor hosts MCP or the CLI | After there are users |
| Cursor-style IDE fork | Own Chromium + the VS Code tree | Not this product |

Cursor's cost is an editor. Continuum's job is to index conversations the user pointed
at, then answer CLI / MCP / a search window. Do not become an IDE to get `.app` and
`.exe`.

Grok Build keeps TUI, headless, and ACP on one agent runtime; desktop shells spawn that
CLI instead of rewriting the agent. Codex CLI is a Rust workspace (`codex-core` plus
TUI / exec / app-server). Continuum already has that **shape**: adapters and
`HistoryStore` are the core; `continuum` CLI, MCP stdio, Vite, and Tauri are shells.
Do not grow a second parser or search engine in the GUI.

### Layers (shells change; the core does not)

```text
┌──────────────────────────────────────────────┐
│ Shell: CLI / MCP / Vite / .app / .exe        │
│ import, search, read, settings               │
└──────────────────┬───────────────────────────┘
                   │ CLI JSON or MCP stdio
┌──────────────────▼───────────────────────────┐
│ Core: Python continuum_history               │
│ adapters, Snapshot v1, HistoryStore, FTS5    │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│ Platform                                     │
│ filesystem, SQLite, process spawn, OS dirs   │
└──────────────────────────────────────────────┘
```

### Stack lock for this repository

- **Core:** Python ≥3.12. Continuum does not run models, tools, sandboxes, or ACP.
  Do not replace `HistoryStore` with a Rust/Go agent runtime.
- **Desktop shell:** Tauri 2 + a PyInstaller `continuum` sidecar. macOS `.app` /
  later `.dmg`; Windows NSIS installer and later a portable `.exe`.
- **Protocol:** GUI talks CLI JSON; agents talk MCP stdio. Allowed commands stay
  `import` / `sources` / `list` / `search` / `read`. No Continuum HTTP API.
- **Frontend:** the existing React/Vite search UI. Do not add a second client store.
- **Not Electron.** Electron is how you ship an IDE.

A Cargo workspace (`crates/agent` + `crates/cli` + `crates/desktop`) is the right
lock for a **coding-agent** product. That is a different repository and a different
product name. Do not stand it up inside this tree or under `$HOME`. If that scaffold
is wanted, name the path and the product first.

Tauri's Rust crate is the desktop host, not a rewrite of the index.

### Artifacts from one commit (target, not current evidence)

```text
dist/
  continuum_history-*.whl   # PyPI / uv; console script continuum
  Continuum.app / .dmg      # macOS desktop
  Continuum-Setup.exe       # Windows installer
  Continuum-portable.exe    # later
```

The CLI must exist even when the desktop shell exists. CI, SSH, and MCP hosts have
no GUI. The desktop shell links the same CLI as a sidecar.

Release matrix (target): `macos-14` (Developer ID + notarization before a public
`.app`), `windows-2022` (Authenticode before a public `.exe`). Version and commit
belong in the artifact; a laptop build is not a release.

Today: GitHub prerelease wheel `v0.1.0a1`; local unsigned macOS `.app`; Windows
`.exe` not built in this workspace; PyPI project `continuum-history` unpublished
(OIDC `invalid-publisher` / 422). Operator steps: [publishing.md](publishing.md).

### Platform differences that are core API, not last-mile polish

- **Index path:** Continuum does not invent `~/.continuum` as the database. The
  index is the `--db` the user passes. Desktop window settings, if added, use OS
  conventions (`~/Library/Application Support/Continuum/` vs `%APPDATA%\Continuum\`),
  never a hardcoded `/Users/...`. Config and cache stay separate from the index.
- **Process:** spawn argv arrays (`Command` / `subprocess` list form). Do not
  concatenate a shell string.
- **Permissions:** a notarized `.app` hits macOS TCC for folder access; a CLI
  started from a terminal often does not. Windows NSIS stays `currentUser`
  (`%LOCALAPPDATA%`), not `C:\Program Files`, unless the user opts in.
- **Signing:** public `.app` needs Developer ID + notarization + staple; public
  `.exe` needs Authenticode. Unsigned builds are internal. Do not home-roll
  “download and overwrite self” on Windows (file locks).
- **Text:** treat files as UTF-8; preserve original newlines on rewrite. Honour
  `HTTPS_PROXY` / `https_proxy` if the desktop ever fetches updates. WinHTTP
  and environment variables are not the same thing.

### Minimum desktop product (P6, still open)

1. Sidecar CLI can import, search, and read; a failed import leaves the previous index.
2. `continuum` / `continuum.exe` from the same wheel on Mac and Windows.
3. Desktop screens: index/source, search, read, settings (index path; proxy later).
4. Never write vendor databases.
5. Auto-update is later; not a custom in-place overwrite.

File trees as an editor, an embedded IDE terminal as the product, a plugin
marketplace, and forking VS Code are out of scope.

### Explicitly rejected

- Forking VS Code / Cursor / Windsurf so the app “looks like Cursor”
- A second agent or search implementation inside Tauri
- Opening this work in `$HOME` instead of this repository
- Installer skin, splash screens, or accounts before the sidecar can import the
  synthetic snapshot on both OS families
- Replacing decision 001 with a Rust agent because Grok did

### Acceptance (do not substitute “the window opened”)

- Same commit: Mac `.app` and Windows `.exe` can import `examples/synthetic.snapshot.json`,
  search a known string, and read to the end
- CLI and desktop share the CLI JSON contract and the same `--db` file
- Unsigned artifacts may be used internally; public distribution requires
  notarization / SmartScreen as applicable
- `uv pip install 'continuum-history==0.1.0a1'` only after the pending publisher
  succeeds. A GitHub wheel is not PyPI

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
console script). Piped / `--format json` success is JSON on stdout; a TTY may print text
instead (`--format auto`). Domain failures are JSON `{"error": ...}` on stderr with exit 2.
`--db` may be omitted when `CONTINUUM_DB` is set; that is still an explicit index, not
home-directory discovery. A bare query (`continuum 数据库锁`) is implicit `search`. `continuum_history.gui` must not import `store` or `adapters`.
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
