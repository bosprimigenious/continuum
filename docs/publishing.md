# Publishing the CLI to PyPI

Operator runbook. This is not a product-status claim.

Distribution name: `continuum-history`. Console script: `continuum`.
Do not publish as `continuum` (that name is a different PyTorch project).
First public version is the existing alpha `0.1.0a1`. Do not bump the version
to retry an upload.

Preferred path: GitHub Actions OIDC Trusted Publishing
(`.github/workflows/publish.yml`). Local `UV_PUBLISH_TOKEN` is a weaker
fallback (`scripts/publish_cli.py`) and is unset in this workspace.

## Current evidence (re-check; do not assume)

Re-run these; do not quote an old chat.

```sh
curl -sS -o /tmp/continuum-history.json -w 'http=%{http_code}\n' \
  https://pypi.org/pypi/continuum-history/json
uv run python scripts/pypi_status.py
```

Recorded 2026-09-20, re-checked the same day:

| Check | Result |
| --- | --- |
| `https://pypi.org/pypi/continuum-history/json` | HTTP 404 `{"message": "Not Found"}` |
| GitHub Environment `pypi` | exists, id `22295702219`, empty, 0 protection rules |
| `Publish CLI to PyPI` run `35454466719` | build green; publish 422 |
| `Publish CLI to PyPI` run `35484452177` | build green; publish 422 (re-dispatch, same claims) |
| `UV_PUBLISH_TOKEN` / `.pypirc` / repo secrets | unset / absent / none |

Publish job error (verbatim):

```text
error: Failed to obtain token for trusted publishing
Caused by: Server returned error code 422 Unprocessable Entity
{"errors":[{"code":"invalid-publisher",
 "description":"valid token, but no corresponding publisher
 (Publisher with matching claims was not found)"}]}
```

OIDC token claims from that run (these must match the pending publisher):

- `repository`: `bosprimigenious/continuum`
- `repository_owner`: `bosprimigenious`
- `job_workflow_ref`: `bosprimigenious/continuum/.github/workflows/publish.yml@refs/heads/main`
- `environment`: `pypi`

The workflow and GitHub Environment are not the bug. PyPI has no matching
publisher (pending or live) for those claims.

## What the maintainer must do on pypi.org

This step cannot be done from the repository. It requires the PyPI account
that will own `continuum-history`.

1. Sign in at [pypi.org](https://pypi.org/).
2. Open [account publishing](https://pypi.org/manage/account/publishing/)
   (pending publisher; the project does not exist yet).
   Do **not** look for a project page named `continuum-history`.
3. Create a GitHub pending publisher with **exactly** these fields:

   | Field | Value |
   | --- | --- |
   | PyPI project name | `continuum-history` |
   | Owner | `bosprimigenious` |
   | Repository | `continuum` |
   | Workflow filename | `publish.yml` |
   | Environment name | `pypi` |

4. Environment name is required because the workflow sets
   `environment: pypi`. Leaving it blank produces the same 422.
5. A pending publisher does **not** reserve the name until the first
   successful upload. If someone else registers `continuum-history` first,
   the pending publisher is invalidated.

## After the pending publisher exists

Do not create `0.1.0a2` or retag.

```sh
gh workflow run "Publish CLI to PyPI" --ref main
gh run watch
uv run python scripts/pypi_status.py
```

Success looks like:

- `https://pypi.org/pypi/continuum-history/0.1.0a1/json` is not 404
- isolated `uv pip install 'continuum-history==0.1.0a1'` (alpha may need
  `--prerelease`) then `continuum --help`

A PyPI CLI upload does **not** make the native adapter READY, does not
notarize `.app`, and does not produce Windows `.exe`.

## What not to do

- Do not bump `0.1.0a1` solely to retry.
- Do not `pip install continuum`.
- Do not commit `UV_PUBLISH_TOKEN` / `.pypirc`.
- Do not delete GitHub release `v0.1.0a1` because PyPI failed.
- Do not treat desktop.yml as this workflow.

## Rollback

- Not uploaded: stopping `publish.yml` does not affect the GitHub wheel.
- Uploaded: PyPI files cannot be deleted; only a higher version can be
  published. Yank is a maintainer action on pypi.org, not a repo script.
- Failed OIDC: keep the GitHub assets; do not change the derived schema.

## Desktop artifacts are a different pipeline

`.app` / `.exe` are Tauri + sidecar (`docs/architecture.md` decision 002,
`.github/workflows/desktop.yml`). They are not on PyPI. Unsigned builds
are internal; public desktop builds need notarization / Authenticode.
