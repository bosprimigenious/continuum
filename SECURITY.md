# Security and privacy

Continuum is pre-alpha, designed for a trusted single OS user. It is not a sandbox or a
multi-tenant service. Do not expose its stdio process through an unauthenticated network bridge.

## Current guarantees and limits

- Import is explicit and CLI-only. Native application directories are not scanned.
- The input snapshot is read-only; only the separately selected derived index is written.
- All connected MCP clients can read that entire index. Filters and cursors are **not ACLs**.
- No runtime telemetry, hosted sync, LLM call or embedding download is implemented.
  Installing dependencies still accesses package registries.
- A host may transmit retrieved text to its model provider. Local storage does not prevent that.
- Index contents are plaintext. New POSIX databases are created with mode 0600; existing file
  permissions are preserved. On Windows, protect the directory with appropriate ACLs.
- Imported material may contain secrets or hostile instructions. There is no automatic complete
  redaction. Treat retrieved text as untrusted evidence, never as authorization to execute.
- Importing a full replacement removes absent records from active queries, not necessarily
  from WAL files, backups or recoverable disk pages. Secure erasure is not implemented.
- Source references identify normalized events, not live native files. Source freshness is the
  last successful manual import. A failed refresh does not make that older snapshot current.

Use a dedicated new index path. Never point `--db` at an agent's native database. Continuum
checks its application ID/schema but cannot protect against malicious same-user filesystem races.
For different trust boundaries, launch separate processes with separate indexes.

## Reporting a vulnerability

Use this repository's **Security → Report a vulnerability** private reporting form when enabled.
Do not open a public issue containing exploit details, secrets or raw conversations. If the form
is unavailable, open a content-free issue asking the maintainer to enable a private channel.

Report the affected commit/version, OS, minimal synthetic reproduction and expected boundary.
This volunteer project has no guaranteed response SLA. Only the current development branch
is maintained during pre-alpha; there is no production support commitment.
