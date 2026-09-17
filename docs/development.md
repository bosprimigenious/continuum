# Development handbook

## Reproduce the foundation gate

```sh
uv sync --locked
uv run python scripts/check.py
```

Individual checks while iterating:

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest --cov --cov-report=term-missing
uv build
uv run python scripts/smoke_wheel.py
```

The wheel smoke uses an isolated environment and a temporary working directory. It verifies the
installed distribution can import the bundled repository's synthetic example and search it,
without importing the source checkout. Tests must never discover the developer's real history.

## Next milestone: one native Cursor path

Do not implement all sources or a desktop shell at once. Complete this one user path:
another developer installs from a checkout, explicitly selects a supported Cursor source,
finds a known conversation through MCP and reads to the end with correct references.

1. Establish a synthetic fixture contract for **one** documented, observed Cursor format.
   Include long conversations, malformed records, duplicate IDs, missing optional data and
   a source changing during capture. Record source version and operating system.
2. Add failing tests for completeness, pagination and diagnostics before the parser.
   Extend the normalized schema deliberately for timestamps/content blocks and coverage;
   do not stuff unparsed native content into a text field and claim complete support.
3. Implement only read-only access. SQLite source connections must use `mode=ro`; cover WAL.
   JSONL must distinguish a partial trailing record from malformed complete input.
4. Connect the adapter to the existing service and four MCP tools. No alternate query engine.
   Preserve errors and source watermarks. Repeating the same input must not add events.
5. With explicit permission, run one live end-to-end test on a named tool/platform version.
   Compare known messages against source records. Store sanitized counts and outcomes only.
6. Have a non-author follow the installation instructions. Record failures and fix them.

Exit evidence: fixture gate green; source unchanged by the reader; no silent omissions in
the supported fixture scope; long records readable to completion; known live record found;
independent install succeeds. Until these pass, say **native adapter NOT READY**.

Then add Claude Code and Codex adapters individually, followed by the GUI search/read path.
An entire product is not finished just because a parser or screenshot works.

## Contribution shape

```text
src/continuum_history/
  models.py          normalized input contract
  adapters/          bounded source readers
  store.py           transactions and shared query service
  cli.py             explicit import and local commands
  mcp_server.py      read-only protocol facade
tests/               synthetic contracts, faults, CLI and stdio integration
examples/            public synthetic data only
scripts/             aggregate gate and installed-wheel checks
```

Use the lockfile. Keep native-format interpretation in adapters and transport behavior in
facades. Do not copy local paths, credentials, raw user messages or personal agent instructions.

## Release checklist

- Run the aggregate gate on the commit being published; inspect its full output.
- Review `git diff --cached` and `git ls-files`; no real logs, databases or private paths.
- Verify CI on the supported foundation matrix; keep live/native checks separate.
- Ensure both READMEs describe implemented, planned and unverified capabilities accurately.
- Inspect the wheel/sdist contents. No native installer/PyPI release until its own gate exists.
- Follow [SECURITY.md](../SECURITY.md); automated hygiene checks are not a full secret audit.

Do not use screenshots, unit coverage or an agent's summary as substitutes for the real path.
