<div align="center">

# CONTINUUM

**Your tools change. Your context stays.**

A local-first history layer for humans and coding agents.

[![CI](https://github.com/bosprimigenious/continuum/actions/workflows/ci.yml/badge.svg)](https://github.com/bosprimigenious/continuum/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Stage: pre-alpha](https://img.shields.io/badge/stage-pre--alpha-orange)

[中文](README.zh-CN.md) · [Architecture](docs/architecture.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

</div>

Coding conversations are scattered across tools. Continuum is being built to let you
find them in one place, read their original context, and make selected history available
to another agent through MCP—without rewriting a vendor's conversation database.

## Where the project stands

**This is a developer foundation, not a ready-to-use history browser.**

| Available in this repository | Not implemented yet |
| --- | --- |
| Versioned normalized snapshot contract and synthetic example | Claude Code / Codex adapters; Cursor JSONL transcripts |
| Atomic SQLite imports, literal Unicode search, source references | Automatic discovery and background incremental updates |
| Version-bound pagination and explicit errors | Desktop installer / Tauri |
| CLI-backed GUI session and Vite shell (pytest only) | Browser e2e, live GUI host |
| CLI and four read-only stdio MCP tools sharing one core | Fine-grained client permissions and attachment reading |
| Cursor IDE `state.vscdb` read-only import through CLI/stdio/wheel (synthetic fixtures) | Live Cursor host verification |
| GitHub prerelease wheel/sdist `v0.1.0a1`; Foundation CI on Linux/macOS/Windows | PyPI `continuum-history`; desktop `.app` / `.exe`; Tauri |
| Unit, rollback, CLI and real stdio protocol tests; CI | Cross-agent execution, cloud sync, semantic search |

No private conversations are included. The example is hand-written synthetic data.
The earlier single-user Cursor prototype is **not** bundled or claimed as native support.

## Try the foundation

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.12+.
There is **no** PyPI package and **no** desktop installer. Do not `pip install continuum`
(that name is a different PyTorch project). GitHub has a prerelease wheel:

```sh
uv pip install \
  https://github.com/bosprimigenious/continuum/releases/download/v0.1.0a1/continuum_history-0.1.0a1-py3-none-any.whl
continuum --help
```

From a checkout:

```sh
git clone https://github.com/bosprimigenious/continuum.git
cd continuum
uv sync --locked

uv run continuum --db .continuum/demo.sqlite3 import examples/synthetic.snapshot.json
uv run continuum --db .continuum/demo.sqlite3 sources
uv run continuum --db .continuum/demo.sqlite3 search "数据库锁"
uv run continuum --db .continuum/demo.sqlite3 list
```

Copy a returned `session_id` from search (or `id` from list):

```sh
uv run continuum --db .continuum/demo.sqlite3 read SESSION_ID --limit 2
```

Pass the returned `next_cursor` with `--cursor` to continue. `null` means the end.
Rerun the import: it reports `"changed": false`. The input file is never modified.

`import` accepts Continuum's normalized snapshot v1 by default. To import one explicitly
selected Cursor IDE `state.vscdb` (not auto-discovered, not a live-host verification):

```sh
uv run continuum --db .continuum/demo.sqlite3 import \
  --adapter cursor-state-vscdb --source-id cursor-demo PATH/TO/state.vscdb
```

Do not commit real Cursor databases. The reader copies the selected file plus WAL/SHM
sidecars and opens the copy with SQLite `mode=ro`; it does not write the source. A damaged
capture (`incomplete_source`) leaves any existing index unchanged and does not create a new
empty `--db`. Other Cursor stores (agent-transcripts JSONL, workspace DBs) are not this adapter.

Reusing a `source_id` replaces that source's entire derived snapshot atomically, including
removing previously indexed events absent from the new snapshot. It is not an archive merge.
Keep your source files; indexes are disposable derived data.

## Connect an MCP client

Start the stdio server using the same index:

```sh
uv run continuum --db .continuum/demo.sqlite3 serve
```

For a host supporting the usual `mcpServers` JSON configuration, adapt this example.
Replace both paths with absolute paths on your machine; configuration location varies by host.

```json
{
  "mcpServers": {
    "continuum": {
      "command": "uv",
      "args": [
        "run", "--locked", "--directory", "/absolute/path/to/continuum",
        "continuum", "--db", "/absolute/path/to/continuum/.continuum/demo.sqlite3", "serve"
      ]
    }
  }
}
```

| Tool | Purpose |
| --- | --- |
| `history_sources` | Inspect imported sources, counts, snapshot digests and index timestamps |
| `history_list` | List sessions with exact source/project filters |
| `history_search` | Search literal text, including short Chinese queries |
| `history_read` | Read complete events in order, with pagination and references |

All four tools query the same local core. They cannot import files, delete source records,
read arbitrary filesystem paths or launch another agent. SDK stdio interoperability is tested;
real Codex / Claude Code / Cursor host integration is **not yet verified**.

**Connecting a client gives it read access to this entire index.** Project filters are not
access controls. Use separate indexes for different trust boundaries. Text retrieved by an
agent may be sent to that agent's model provider, even though Continuum has no upload service.

## Architecture and stack

```text
Source adapters → normalized snapshots → local history core → CLI
                                             │             → MCP (stdio)
                                         SQLite / FTS5     → GUI (CLI JSON; Vite shell)
```

- **Core:** Python 3.12+, Pydantic v2 contracts, SQLite + FTS5, official MCP Python SDK v2.
- **Tooling:** uv and a committed lockfile; pytest, Ruff, mypy; GitHub Actions.
- **GUI:** React + TypeScript + Vite talks to the index through the `continuum` CLI JSON
  interface (`continuum_history.gui`). Run `npm install && npm run dev` in `gui/` from a
  checkout. Browser end-to-end tests and Tauri are **not** implemented.
- **Deployment:** one local modular application. No account, cloud database, vector service,
  model download or LLM API is needed for the current demo.

The core must remain independent of MCP, the GUI and vendor formats. Packaging the Python
core with a desktop shell requires a platform-specific spike before committing to a release.
See [architecture, trade-offs and migration boundaries](docs/architecture.md).

## Development

```sh
uv sync --locked
uv run python scripts/check.py
```

The aggregate gate checks formatting, lint, strict source typing, tests with a coverage floor,
basic publication hygiene, wheel/sdist builds, and a wheel installed in an isolated environment.
It may download build/runtime dependencies. It does not read your native agent history.

CI runs the same gate on Linux, macOS and Windows. A green run validates the **foundation**,
not native source coverage, a real MCP host, or a packaged app. Read [the next bounded milestone](docs/development.md)
before adding features. Adapter work starts with synthetic fixtures and failing behavior tests.
PyPI upload, when enabled, uses GitHub OIDC Trusted Publishing (`publish.yml`); it is still
blocked until a pending publisher is registered on PyPI.

## Scope

The first product milestone is reliable read-only history: discover supported local records,
show coverage and errors, search and read through a GUI or MCP. Start with one Cursor path,
prove it, then extend to Claude Code and Codex.

Execution orchestration, automatic migration/cleanup, shared cloud memory and model routing
are out of scope for this milestone. Existing projects are welcome references; novelty is
not the acceptance criterion. Correctness, understandable boundaries and a complete user path are.

## Privacy and license

Local indexes contain plaintext. There is no automatic secret redaction or secure-erasure guarantee.
Only import material you intend to expose to the connected client. See [SECURITY.md](SECURITY.md).

[MIT](LICENSE). Continuum is an independent project, not affiliated with any agent vendor.
The working name does not imply exclusive naming or trademark rights.
