# UI development

How to work on `packages/ui`. For how it is built, see [architecture](architecture.md). General set-up for the whole repository is in the [project development notes](../../../docs/development.md).

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

- Plain JavaScript with JSX. Call Python only through `src/api/`.
- Put styles in CSS files; the content security policy forbids inline scripts and styles.
- The interface uses Fluent UI (`@fluentui/react-components`). Colours live in one place, `src/theme.js`, built from the logo in `brand/` (amber to red-orange, maroon, near-black neutrals), with red for danger and amber for warnings. Fluent adds its styles through the browser's style API, which Cornea's default `style-src 'self'` blocks. The window therefore uses that policy with `'unsafe-inline'` added to `style-src` only (scripts stay strict).
- Node version is in `.nvmrc`.

```bash
npm run dev       # Vite dev server
npm run build     # writes dist/
npm run lint      # ESLint
npm test          # Vitest, Testing Library and an accessibility check
npm run format    # Prettier
```

- One small component per file, with a test beside it (`Name.jsx`, `Name.test.jsx`). The folders are described in [architecture](architecture.md#frontend).
- Lists and option definitions live as JSON in `src/data/`, not in components.
- Name plain JavaScript modules in lower case (`inherited.js`) and components in PascalCase (`Card.jsx`).
- The project type-checks JavaScript through `jsconfig.json`, so give props and callbacks JSDoc types.

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

Frontend tests use Vitest and Testing Library with `fetch` mocked, query by role and label, and run an accessibility check on each component. A test that reads what the page sent should go through a small helper that types the mock's calls, as in `Card.test.jsx`.

### Smoke test the compiled build

`scripts/smoke/` builds the compiled wheel, with the built front end inside it, and tries it in
a fresh virtual environment. It is a manual check, separate from the Vitest and pytest suites,
and it needs network access and a C compiler. The scripts are PowerShell, so the check runs on
Windows, and `setup_venv.ps1` expects Python 3.11 (`py -3.11`). It installs the compiled core and
API wheels, so run core's smoke `setup_venv.ps1` and then the API's first. The front end is built with `npm`
when `src/rayohx_ui/ui/dist` is missing.

```powershell
./scripts/smoke/setup_venv.ps1   # builds the wheel and installs it into scripts/smoke/.venv
./scripts/smoke/test_ui.ps1      # starts the compiled window without a window and runs the checks below
```

`test_ui.ps1` starts `rayohxu --no-window` and waits up to about 30 seconds for it to print its
address. It loads that address, which starts the session the API calls need, then POSTs the
**first line** of `scripts/smoke/test_links.txt` to `/api/v1/inspect` and prints the result. It
fails if the app exits or prints no address, and it stops the app when it finishes. To try
another stream, put its URL on the first line of that file; any further lines are ignored.
`test_links.txt` is kept in the repository, so use a stream you are allowed to share. The app's
output goes to `ui.out.log` and `ui.err.log` in the same folder.

The virtual environment, `wheels/` and logs under `scripts/smoke/` are git-ignored.
