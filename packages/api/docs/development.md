# API development

How to work on `packages/api`. For how it is built, see [architecture](architecture.md); for running it, see [api](api.md). General setup for the whole repository is in the [project development notes](../../../docs/development.md).

## Set up

```bash
uv sync --locked                  # all packages and the dev tools
cp .env.example .env              # set RAYOHX_API_API_KEYS, or RAYOHX_API_AUTH_MODE=none
uv run python -m rayohx_api       # http://127.0.0.1:8000
```

Set `RAYOHX_API_DOCS_ENABLED=true` to get `/docs` and `/redoc` while you work.

## Checks

Run only what your change touches:

```bash
uv run pytest packages/api/tests/unit --no-cov             # unit tests
uv run pytest -m integration packages/api/tests --no-cov   # integration and contract tests
uv run ruff check packages/api
uv run ruff format --check packages/api
uv run mypy packages/api/src
```

The `--no-cov` flag is needed because the coverage threshold in `pyproject.toml` applies to the whole repository, not one package. CI runs the same commands per package (`ci-api.yml`), plus pre-commit on the package's files.

Tests live in `packages/api/tests`: unit tests in `unit/` and integration tests in `integration/`. `tests/conftest.py` stays at the top because it applies to both: it gives every test fresh settings and marks everything under `integration/` as an integration test. Test behaviour through the app: build it with `create_app()` and call it with Starlette's `TestClient`. The integration tests start the real server and check it against `/openapi.json`.

## Adding an endpoint

1. Add the request and response models to the matching file in `schemas/v1/` (or a new one, re-exported from `schemas/v1/__init__.py`), with `Field` descriptions, examples and a maximum length on every string.
2. Add the handler to the matching file in `routers/v1/` (or a new one, included in `routers/v1/__init__.py`). Keep it thin: validate, call `rayohx`, return the model. Annotate the return type, use plain `def` for anything that can block, and declare every non-200 response in `responses=`.
3. Map library errors to HTTP errors in the router. Never return the text of an unexpected exception.
4. Protect it with `Depends(authenticate)` unless it is a probe.
5. Add tests for the behaviour and for each status code the route declares.
6. Regenerate the contract: `uv run python packages/api/scripts/export_openapi.py`, and commit [`openapi.json`](openapi.json). CI fails if it is out of date.
7. Update [api](api.md) (endpoints table), [security](security.md) if you added a protection, and the `[Unreleased]` section of `packages/api/CHANGELOG.md`.

A breaking change goes in a new `/api/v2` router, not in `/api/v1`.

## Adding a setting

Add it to `Settings` in `config.py`, read it through `get_settings()` (never `os.environ`), and add a row to the settings table in [api](api.md) and the package `README.md`.

## Compiled releases (.pyd / .so)

A release ships one compiled module, not plain `.py` sources. `setup.py` compiles the whole `rayohx_api` package with Nuitka into a single binary when `PYD_BUILD=1`; the `release-api` workflow sets it and builds one wheel per OS, architecture and Python version with cibuildwheel. Each wheel is tested with the unit tests before it is published.

- The binary is `rayohx_api.<tag>.pyd` on Windows and `rayohx_api.<tag>.so` on Linux and macOS, with every submodule inside it. No sdist is published, so a platform without a wheel cannot install `rayohx-api`.
- Nuitka needs a C compiler (MSVC, gcc or clang). `--mingw64` is not available on Python 3.13 or newer.
- `python -m rayohx_api` does not work on the compiled build because `__main__` is embedded in the binary. The `rayohx-api` command does.
- Compiling is obfuscation, not encryption: it raises the effort needed to read the code but does not make it secret.
- Without `PYD_BUILD`, `uv sync`, tests and coverage run against the plain sources. To try it locally, run `PYD_BUILD=1 uv build --wheel --package rayohx-api`. CI does this on every change and checks that the wheel holds the binary and its `.pyi` stub but no sources.
- `stubgen` writes one `.pyi` per module into a `rayohx_api/` folder beside the binary (no `__init__.py`, so Python still loads the binary), so `rayohx-ui` and other users still get type checking. The stubs show signatures and docstrings, not implementations.
- Nuitka supports Python 3.15 only experimentally (as of 4.3.5), so watch that wheel in the release matrix.
- Release with the tag `api-v<version>` after the core. The tag must equal the version in `pyproject.toml`, and the `api` environment must exist with trusted publishing set up on PyPI.

### Smoke test the compiled build

`scripts/smoke/` builds the compiled wheel and tries it in a fresh virtual environment. It is a
manual check, separate from the pytest suites, and it needs network access and a C compiler.
The scripts are PowerShell, so the check runs on Windows, and `setup_venv.ps1` expects
Python 3.11 (`py -3.11`). It installs the compiled core wheel, so run core's smoke
`setup_venv.ps1` first.

```powershell
./scripts/smoke/setup_venv.ps1   # builds the wheel and installs it into scripts/smoke/.venv
./scripts/smoke/test_api.ps1     # starts the compiled server and runs the checks below
```

`test_api.ps1` starts `rayohx-api` on port 8765 with authentication off, waits up to about 30
seconds for `/health` to answer, then POSTs the **first line** of `scripts/smoke/test_links.txt` to
`/api/v1/inspect` and prints the result. It fails if the server exits or does not become ready, and
it stops the server when it finishes. To try another stream, put its URL on the first line of that
file; any further lines are ignored. `test_links.txt` is kept in the repository, so use a stream
you are allowed to share. Downloads, the database and logs go to `scripts/smoke/data`.

The virtual environment, `wheels/`, `data/` and logs under `scripts/smoke/` are git-ignored.

## Rules to keep

- Log with the `logging` module, never `print`, and never log keys or request bodies.
- Do not add global state; settings are the one cached object.
- Do not turn protections off to make a test pass. Use `RAYOHX_API_AUTH_MODE=none` in a test's environment instead.
- Explain any `# noqa` or `# nosemgrep` with a reason in the comment.
