# UI development

How to work on `packages/ui`. For how it is built, see [architecture](architecture.md). General set-up for the whole repository is in the [project development notes](../../../docs/development.md).

> The interface is not built yet; the frontend is an example app and some sections below are placeholders.

## Set up and run

```bash
uv sync --locked
npm ci --prefix packages/ui/src/rayohx_ui/ui
npm run build --prefix packages/ui/src/rayohx_ui/ui
uv run python -m rayohx_ui                 # window (Windows only)
uv run python -m rayohx_ui --no-window     # prints an address for a browser
uv run python -m rayohx_ui --dev           # Vite with hot reload (needs Node)
```

`--dev` starts `npm run dev` through Cornea and relaxes the content security policy for Vite. Use it only while developing.

## Writing the frontend

- Plain JavaScript with JSX. Call Python only through `src/api.js`.
- Put styles in CSS files; the content security policy forbids inline scripts and styles.
- Add UI kits such as Fluent UI as optional dependencies when needed; none is included.
- Node version is in `.nvmrc`.

```bash
npm run dev       # Vite dev server
npm run build     # writes dist/
npm run lint      # ESLint
npm test          # Vitest, Testing Library and an accessibility check
npm run format    # Prettier
```

*Placeholder:* component conventions, folder structure and design guidelines.

## Checks

Run only what your change touches:

```bash
uv run pytest packages/ui/tests/unit --no-cov
uv run pytest -m integration packages/ui/tests --no-cov
uv run ruff check packages/ui
uv run ruff format --check packages/ui
uv run mypy packages/ui/src
```

The package's pytest settings require 80% coverage, so a run of a few tests fails on coverage unless you pass `--no-cov`. CI runs the same checks (`ci-ui.yml`), plus the frontend lint, tests and build.

## Tests

```text
packages/ui/tests/
  unit/          replace Cornea's Shell, so no window opens
  integration/   Windows only: a real server without a window (needs a built dist), and the built rayohxu.exe
  frozen.py      helpers for the frozen-build tests
```

Tests in `integration/` are marked `integration` automatically and are excluded from the default run.

*Placeholder:* frontend test conventions and end-to-end tests.
