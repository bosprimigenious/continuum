# Contributing to Continuum

Thanks for helping make local conversation history accessible and trustworthy.

Start with [the development handbook](docs/development.md) and [architecture](docs/architecture.md).
For substantial changes, discuss one concrete user behavior in an issue before adding scope.
Small fixes and tests are welcome directly as pull requests.

## Working agreement

1. Install with `uv sync --locked`.
2. Write a failing behavior test using synthetic fixtures. Missing dependencies are not a TDD red.
3. Make the smallest implementation that satisfies the contract; refactor with tests green.
4. Run `uv run python scripts/check.py` and include exact results in the PR.
5. Update English and Chinese README capability statements if behavior changes.

Never attach native conversation databases, real logs, access tokens, local config or private
paths to a public issue. Reduce bugs to synthetic inputs. Mark platform/tool versions as
untested until actually exercised. Read-only access, explicit errors and provenance are required.

Do not weaken assertions or remove fixtures to make a gate green. Contract changes need an
explanation and migration boundary. A claim of completion needs executable evidence.

Commit messages should describe the actual change, for example `fix(search): preserve empty filters`.
Keep unrelated formatting, dependency upgrades and refactors out of a focused PR.

Be respectful and specific in reviews. Critique behavior and code, not people. Contributors
retain copyright in their contributions and contribute under this repository's MIT license.
