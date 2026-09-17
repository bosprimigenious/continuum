# Contributor and agent instructions

Read README.md and docs/development.md before changing behavior. This is the Continuum
repository; do not change global agent configs or other repositories while working here.

- Use Python 3.12+ and uv.lock. Do not introduce another package manager for the Python core.
- Run `uv run python scripts/check.py` before claiming the foundation passes.
- Use synthetic fixtures; no automatic discovery of a contributor's private history in tests.
- Preserve source data. All database writes belong to the explicitly selected derived index.
- Native adapters and GUI are planned, not implemented. Update status with evidence, not intent.
- Keep the core independent of MCP and GUI; do not hand-roll protocol negotiation.
- TDD: add a behavior-level failing test, implement, refactor, rerun the aggregate gate.
- Scope changes and schema migrations require explicit rationale and rollback instructions.
- Do not commit secrets, real logs, personal instructions, machine paths or migration archives.
- Report failing commands and untested compatibility combinations honestly.
