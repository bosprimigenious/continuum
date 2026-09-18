# Contributor and agent instructions

Read README.md and docs/development.md before changing behavior. This is the Continuum
repository; do not change global agent configs or other repositories while working here.

- Use Python 3.12+ and uv.lock. Do not introduce another package manager for the Python core.
- Run `uv run python scripts/check.py` before claiming the foundation passes.
- Use synthetic fixtures; no automatic discovery of a contributor's private history in tests.
- Preserve source data. All database writes belong to the explicitly selected derived index.
- Native Cursor `state.vscdb` read-only import exists for synthetic fixtures. Live Cursor
  hosts, other Cursor formats and other tools are unverified. A CLI-backed GUI session and
  Vite shell exist; browser e2e and Tauri are unverified. Update status with evidence, not intent.
- Keep the core independent of MCP and GUI; do not hand-roll protocol negotiation.
- TDD: add a behavior-level failing test, implement, refactor, rerun the aggregate gate.
- Scope changes and schema migrations require explicit rationale and rollback instructions.
- Do not commit secrets, real logs, personal instructions, machine paths or migration archives.
- Report failing commands and untested compatibility combinations honestly.

## Continuing development

- Start in this repository root, inspect `git status --short`, and preserve existing local work.
- Read the continuation entry in `docs/development.md`; implement its bounded milestone when
  asked to develop. Directly inspect and modify code, not just produce another plan document.
- Native Cursor path priority remains P1 (synthetic input through CLI/stdio/wheel), then live
  host, then other sources. The user started P5-a: a GUI that shells out to the continuum CLI
  JSON interface and reuses the pytest harness. Do not start P6 Tauri, an HTTP Continuum API,
  execution orchestration, cloud accounts or a stack rewrite.
- Run the existing aggregate gate before changes and after implementation. Carry baseline
  failures forward explicitly; do not skip them or lower the coverage floor.
- Preserve regression coverage for unrelated databases, cursor scope/revision, Unicode output,
  platform-specific file metadata, source mutation, rollback and safe MCP errors.
- Keep one current development handbook. Update it when decisions change; do not create a new
  product-plan version for each discussion. Competitor discovery alone is not a scope change.
- For agent-driven work, do not commit, push, publish, remove files or change global settings
  unless the user's request authorizes that action. Keep local cleanup out of feature work.
- Report implemented behavior, commands/results, known failures and untested live/platform
  combinations separately. A passing foundation gate does not make the full product READY.
