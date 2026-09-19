<div align="center">

<img src="gui/src-tauri/icons/icon.png" width="96" height="96" alt="Continuum">

# Continuum

**Your tools change. Your context stays.**

Local conversation history for humans and coding agents.
Import what you point at. Search it. Read it to the end. Hand a slice to another agent over MCP.
Never rewrite a vendor database.

[![CI](https://github.com/bosprimigenious/continuum/actions/workflows/ci.yml/badge.svg)](https://github.com/bosprimigenious/continuum/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/bosprimigenious/continuum?include_prereleases)](https://github.com/bosprimigenious/continuum/releases)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![pre-alpha](https://img.shields.io/badge/status-pre--alpha-orange)

[中文](README.zh-CN.md) · [Architecture](docs/architecture.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Releases](https://github.com/bosprimigenious/continuum/releases)

</div>

---

Continuum is a **local** index of conversations you already have on disk.
You choose a file. Continuum copies what it can into a derived SQLite database.
CLI, MCP, and the GUI all query that same index.

It does **not** scan your home directory, does **not** write Cursor/Claude/Codex stores,
and does **not** upload chats. Pre-alpha: the Cursor path is synthetic-fixture green;
a live host is not verified. PyPI is not published yet.

## Contents

- [Try it](#try-it)
- [Install](#install)
- [CLI](#cli)
- [MCP](#mcp)
- [GUI](#gui)
- [What works / what does not](#what-works--what-does-not)
- [How it is put together](#how-it-is-put-together)
- [Contributing](#contributing)
- [Privacy](#privacy)
- [FAQ](#faq)
- [License](#license)

## Try it

Need [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.12+.

```sh
git clone https://github.com/bosprimigenious/continuum.git
cd continuum
uv sync --locked

uv run continuum --db .continuum/demo.sqlite3 import examples/synthetic.snapshot.json
uv run continuum --db .continuum/demo.sqlite3 search "数据库锁"
```

You should see one hit whose preview contains `SQLite 数据库锁`. Copy `session_id`, then:

```sh
uv run continuum --db .continuum/demo.sqlite3 read SESSION_ID --limit 2
```

Follow `next_cursor` until it is `null`. Import the same file again: `"changed": false`.
The example file is never modified.

The demo data is hand-written synthetic JSON. There are no private chats in this repository.

## Install

**Do not `pip install continuum`.** That name is an unrelated PyTorch library.

| Channel | Status |
| --- | --- |
| GitHub prerelease wheel `v0.1.0a1` | Available |
| PyPI project `continuum-history` | Not published |
| Signed desktop installer | Not published |
| Windows `.exe` | Not built |

From the GitHub release:

```sh
uv pip install \
  https://github.com/bosprimigenious/continuum/releases/download/v0.1.0a1/continuum_history-0.1.0a1-py3-none-any.whl
continuum --help
```

From a checkout, use `uv run continuum …` as in [Try it](#try-it). The console script is
`continuum`; the distribution name will be `continuum-history` when it reaches PyPI.

## CLI

All commands take an explicit `--db` path. That file is Continuum's index, never a vendor DB.

```sh
# Normalized snapshot v1 (default adapter)
uv run continuum --db .continuum/demo.sqlite3 import examples/synthetic.snapshot.json
uv run continuum --db .continuum/demo.sqlite3 sources
uv run continuum --db .continuum/demo.sqlite3 list
uv run continuum --db .continuum/demo.sqlite3 search "数据库锁"
uv run continuum --db .continuum/demo.sqlite3 read SESSION_ID --limit 2
```

Search is literal Unicode (including short Chinese). Results return a 240-character **preview**;
`read` returns full event text. Filters on source/project are exact match, not permissions.

### Cursor `state.vscdb`

One observed IDE shape, not every Cursor store. You pass the file. Continuum does not find it
for you. Live Cursor installs are **unverified**.

```sh
uv run continuum --db .continuum/demo.sqlite3 import \
  --adapter cursor-state-vscdb --source-id cursor-demo PATH/TO/state.vscdb
```

`--source-id` is required. The reader copies the main file plus WAL/SHM, then opens the copy
with SQLite `mode=ro`. A blocked capture (`incomplete_source`) leaves any existing index
unchanged and does not create a new empty `--db`.

Do not commit real Cursor databases. Agent-transcripts JSONL and workspace sidebar DBs are
not this adapter. Reusing a `source_id` **replaces** that source's derived snapshot; it is
not an archive merge. Keep the original files. Indexes are disposable.

## MCP

Same index, four read-only tools. Import is CLI-only.

```sh
uv run continuum --db .continuum/demo.sqlite3 serve
```

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

Replace both paths. Host config file locations differ.

| Tool | Does |
| --- | --- |
| `history_sources` | Imported sources, counts, digests, timestamps |
| `history_list` | Sessions, optional source/project filter |
| `history_search` | Literal substring search |
| `history_read` | Full events, pagination, `source_ref` |

There is no import tool, no filesystem path argument, no delete, no “run this in another agent”.
stdio against the Python SDK is tested. Cursor / Claude Code / Codex **hosts** are not.

**A connected client can read the entire selected index.** Project filters are not ACLs.
Use one index per trust boundary. Text an agent reads may still be sent to that agent's
model provider. Continuum has no upload service of its own.

## GUI

The UI talks to the same CLI JSON interface. It does not parse vendor files or open SQLite
itself.

**Vite shell** (checkout, not a downloadable app):

```sh
cd gui
npm install
npm run dev
```

**Desktop** is experimental. This repo can build an **unsigned** macOS `.app` with a
PyInstaller sidecar of the `continuum` CLI. That artifact is not notarized, not shipped
in git, and not a clean-machine install. Windows `.exe` is not produced in this tree.

```sh
uv run --with pyinstaller python scripts/build_sidecar.py
uv run python scripts/smoke_sidecar.py
cd gui && npm ci && npx tauri build
```

Needs Rust (`rustup`) and Node. Output lands under
`gui/src-tauri/target/release/bundle/` (gitignored).

## What works / what does not

Pre-alpha. A green foundation gate means the **checkout** works, not that the product is done.

| Works in this repository | Not here yet |
| --- | --- |
| Snapshot v1 import, literal search, pagination, source refs | Claude Code / Codex adapters |
| Cursor `state.vscdb` / `cursorDiskKV` (synthetic fixtures) | Live Cursor host, Cursor JSONL, sidebar DBs |
| CLI + four read-only MCP tools on one core | Auto-discovery, background refresh |
| GUI session via CLI JSON; Vite dev; unsigned local macOS `.app` | Browser e2e, signed/notarized installer, Windows `.exe` |
| GitHub `v0.1.0a1` wheel; CI on Linux / macOS / Windows | PyPI `continuum-history` |
| Rollback, Unicode, WAL sidecar, stdio tests | Semantic search, attachments as full text, cloud sync |

Native adapter status: **NOT READY** until a named live Cursor/OS/MCP-host combination is recorded.
GUI status: **NOT READY** until a real browser (or desktop) path is exercised end to end.

## How it is put together

```text
adapters  →  Snapshot v1  →  HistoryStore (SQLite + FTS5)
                                  │
                     CLI JSON ────┼──── MCP stdio (read-only)
                                  │
                     GUI / Tauri ─┘  (spawn continuum, no extra API)
```

One Python core. Clients do not grow a second search engine.
See [docs/architecture.md](docs/architecture.md) for contracts, rejected alternatives,
and how a failed import is supposed to behave.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/development.md](docs/development.md)
before changing behavior.

```sh
uv sync --locked
uv run python scripts/check.py
```

That gate is format, lint, strict mypy, tests (coverage floor 85%), a basic publication
hygiene scan, wheel/sdist, and an isolated wheel smoke. It may hit the network for build
dependencies. It does **not** read your private agent history.

Please:

- Start from synthetic fixtures and a failing behavior test.
- Keep vendor databases read-only.
- Do not attach real `state.vscdb`, logs, or tokens to issues or PRs.
- Do not skip a red test or lower the coverage floor to go green.

CI runs the same gate on Ubuntu, macOS, and Windows.

## Privacy

Indexes are plaintext. There is no automatic secret redaction and no secure-erase guarantee.
Only import what you are willing to expose to every client connected to that `--db`.
Details: [SECURITY.md](SECURITY.md).

## FAQ

**Why isn't this `pip install continuum`?**
PyPI already has [continuum](https://pypi.org/project/continuum/), a PyTorch continual-learning
library. This project will publish as `continuum-history`. Until then, use the GitHub wheel
or a checkout.

**Does Continuum phone home?**
No runtime telemetry, hosted sync, or model API. `uv` / `npm` / `cargo` still talk to package
registries when you install or build.

**Will connecting MCP leak my whole library?**
The tools can read everything in **that** index. Split indexes if you need split trust.
Whatever the host does with the text is outside Continuum.

**Can I point `--db` at Cursor's own database?**
No. `--db` is Continuum's derived index. Pass the vendor file to `import`.

**Is the macOS `.app` a release?**
No. It is a local packaging spike: unsigned, not notarized, not installed from GitHub Releases.

## License

[MIT](LICENSE). Copyright (c) 2026 Continuum contributors.

Independent project. Not affiliated with Cursor, Anthropic, OpenAI, or any other vendor.
The name does not claim exclusive trademark rights.
