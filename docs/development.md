# Development

Repository-wide set-up and tooling. Each package documents its own development: [core](../packages/core/docs/development.md), [CLI](../packages/cli/docs/development.md), [API](../packages/api/docs/development.md), [UI](../packages/ui/docs/development.md) and [Docker](../packages/docker/docs/development.md).

## Layout

```text
packages/core/     the `rayohx` library: all the logic, never prints or exits (typed)
packages/cli/      the `rayohx` command (Typer + Rich): parses input, calls the library, shows output
packages/api/      the `rayohx_api` FastAPI app: routers, schemas, errors, settings, OpenAPI contract
packages/ui/       the `rayohxu` window (Cornea Shell) and its React + Vite frontend
packages/docker/   the container image
installer/         shared installer pieces: NSIS behavior and pinned tool versions
scripts/           repository settings and the shared installer build helpers
docs/              repository-wide documentation
pyproject.toml     workspace metadata and tool configuration
uv.lock            locked dependencies (commit this file)
```

Each package has its own `src/`, `tests/` (with `unit/` and `integration/`), `docs/` and `CHANGELOG.md`. The core library never imports the other packages; the CLI, API and UI build on it.

## Tooling

| Purpose | Tool |
| --- | --- |
| Environment, dependencies, build | [uv](https://docs.astral.sh/uv/) with Hatchling |
| Lint and format | Ruff |
| Type checking | mypy (strict) |
| Tests and coverage | pytest with pytest-cov (80% minimum) |
| API | FastAPI, uvicorn, pydantic-settings; Schemathesis for contract tests |
| Window | `cornea-shell` (Windows only) |
| Frontend | Node 22 or newer, Vite, React, Vitest, ESLint, Prettier |

```bash
uv sync --locked           # create .venv and install every package and the dev tools
uv run pytest packages/<name>/tests/unit --no-cov           # one package's unit tests
uv run pytest -m integration packages/<name>/tests --no-cov # its integration tests
uv run ruff check packages/<name>
uv run mypy packages/<name>/src
```

Run only what your change touches. Integration tests are marked `integration` automatically, excluded from the default run, and run as their own CI jobs.

## Continuous integration

Each package has its own workflows: `ci-<package>.yml`, `audit-<package>.yml`, `security-<package>.yml` and `release-<package>.yml`, plus repository-wide `ci-repo.yml`, `audit-repo.yml` and `security-repo.yml`. Each CI workflow ends in a gating job, and these are the required checks in the branch ruleset. Tests run on Linux (Python 3.11 to 3.15), and on Windows, macOS and Linux ARM64 (Python 3.11), as each package's workflow defines.

## Releasing

Releases are routed by tag and published with trusted publishing, so no API token is stored. See [releasing](releasing.md), and each package's `packaging.md` for the details.
