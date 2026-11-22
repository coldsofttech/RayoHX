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

## Rules to keep

- Log with the `logging` module, never `print`, and never log keys or request bodies.
- Do not add global state; settings are the one cached object.
- Do not turn protections off to make a test pass. Use `RAYOHX_API_AUTH_MODE=none` in a test's environment instead.
- Explain any `# noqa` or `# nosemgrep` with a reason in the comment.
