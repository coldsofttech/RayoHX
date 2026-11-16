# Development

## Layout

```text
src/rayohx/           library: all the logic, never prints or exits (typed)
src/rayohx_cli/       Typer + Rich command line: parses input, calls the library, shows output
src/rayohx_api/       FastAPI app: routers, schemas, errors, settings (see api.md)
src/rayohx_ui/        Cornea Shell wiring and the `rayohx-ui` command (see ui.md)
src/rayohx_ui/ui/     React + Vite frontend (JavaScript)
tests/                 pytest tests, one folder per component: core/, cli/, api/, ui/ (each with integration/)
installer/             window spec and NSIS script, shared helpers, pinned tool versions (the command line's are in packages/cli/installer/; see packaging.md)
scripts/               repository settings, OpenAPI export, installer build, release manifests
docs/                  documentation, including the generated openapi.json
pyproject.toml         metadata, dependencies and tool configuration
uv.lock                locked dependencies (commit this file)
```

The example names are `rayohx` (library), `rayohx_cli` (command line package), `rayohx_api`, `rayohx_ui`, and the commands `rayohx` and `rayohx-ui`. After creating a repo from this template, run the **Init** workflow with a short lowercase `name` (for example `acme`) and a display `title` (for example "Acme Studio"). It opens a pull request that:

- replaces the owner and repository name;
- renames the packages (`acme_package`, `acme_cli`, `acme_api`, `acme_ui`), the commands (`acme-cli`, `acme-ui`), the settings prefix (`ACME_API_`) and the app id, and replaces "RayoHX" with your title;
- generates new product GUIDs for the Windows installers, then regenerates `uv.lock` and `docs/openapi.json`.

The rename is `scripts/init_template.py` (it replaces only those exact patterns, so prose such as "for example" is left alone, and it deletes itself afterwards). The workflows and the installer scripts read names from `pyproject.toml` (`[project.scripts]` and `[tool.installer]`, through `installer/projectinfo.py`), so they need no renaming. If you add a new place that uses an example name, keep it in one of the patterns the script knows.

What is left for you:

1. Replace the window icon (`src/<ui package>/ui/public/icon.png`).
2. Set the description and URLs, and add an email to the author, in `pyproject.toml`.
3. Review the pull request for lines that still say "example" (the script lists them).
4. Replace the example React app, API routes and window action.

See [packaging](packaging.md) and [releasing](releasing.md) for the installers and the first-release checklist.

Commands, options and exit codes are documented in the [command line guide](guides/cli.md).

## Adding a command

The command line only reads options and shows results; the work belongs in the `rayohx` library.

1. Add the logic to `rayohx` as a plain function that returns a value or raises an exception. It must not print or exit.
2. Add a module for the command in `src/rayohx_cli/cli/` (see `info.py` and `download.py`) that calls it, registers it on the `app` from `root.py`, and writes through the consoles in `output.py`. Put options shared with other commands in `src/rayohx_cli/params/`, and import the module in `src/rayohx_cli/cli/__init__.py` so it is registered.
3. Add a `--json` option if the command returns data.
4. Add tests with `typer.testing.CliRunner` in `tests/cli/unit/`, mirroring the module's place in `rayohx_cli`.
5. Document the command in the [command line guide](guides/cli.md): a page under `guides/cli/`, and a row in its contents and command tables.

Unexpected exceptions are caught by `run()` in `src/rayohx_cli/cli/__init__.py`: they print a one-line message to stderr and show a traceback only with `--verbose`. Local variables are never shown, because they can contain secrets.

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
uv sync                    # create .venv and install dev dependencies
uv run pytest              # unit tests with coverage (skips integration tests)
uv run pytest -m integration --no-cov   # integration tests only
uv run ruff check .        # lint
uv run ruff format .       # format
uv run mypy                # type check
uv build                   # build the sdist and wheel (core library and command line only)
```

Frontend, from `src/rayohx_ui/ui` (or with `--prefix`):

```bash
npm ci                     # install exactly what package-lock.json says
npm run dev                # Vite dev server; `uv run python -m rayohx_ui --dev` wraps it in the window
npm run build              # writes dist/, which the window serves and the Windows installer freezes in
npm run lint && npm test   # ESLint, Vitest
npm run format             # Prettier
```

Other useful commands:

```bash
uv run python -m rayohx_api              # run the API on its own (see api.md)
uv run python scripts/export_openapi.py   # regenerate docs/openapi.json
uv run python -m rayohx_ui --no-window   # serve the UI for a browser
```

## Integration tests

Tests are grouped by component: `tests/core/`, `tests/cli/`, `tests/api/` and `tests/ui/`. Each has an `integration/` folder, and tests in any `integration/` folder are marked `integration` automatically by `tests/conftest.py`. Run one component with, for example, `uv run pytest tests/api --no-cov`. They are excluded from the default `pytest` run, and therefore from the pre-commit hook, and run as their own job in CI. Put slower or end-to-end tests there. They include a real API server, a Schemathesis contract test and, on Windows with a built frontend, a real Cornea server without a window.

## Continuous integration

The `ci` workflow runs six jobs: `lint` (pre-commit including Ruff, mypy, ESLint and Prettier, plus the generated-file checks), `ui` (frontend lint, tests and build), `test` (unit tests), `integration` (tests marked `integration`), `ui-windows` (the real Cornea test against the built frontend), and `build` (the wheel, `twine check`). The `test` and `integration` jobs run on Python 3.11 to 3.15 on Ubuntu, and on 3.11 on Windows and macOS. A final `ci` job gates on all of them and is the single required check in the branch ruleset.

## Releasing to PyPI

This section covers the PyPI side. Installers, signing and the package managers are in [releasing](releasing.md) and [packaging](packaging.md).

Publishing uses [trusted publishing](https://docs.pypi.org/trusted-publishers/), so no API token is stored.

1. On PyPI, add a trusted publisher for this repository: workflow `release.yml`, environment `pypi`.
2. Create an environment named `pypi`. The settings script does this and restricts it to `v*` tags.
3. Bump `__version__` in `src/<package>/__init__.py` and update `CHANGELOG.md`.
4. Publish a GitHub release tagged `v<version>`. The workflow fails if the tag and version differ.

## Media test files

The muxer tests use small real MPEG-TS and fragmented MP4 files in `tests/fixtures/media` (about 860 KB), including two complete HLS sets with separate audio. They were made by FFmpeg so that RayoHX's output can be compared with something it did not write. To regenerate them, run `python scripts/make_media_fixtures.py` (needs `ffmpeg` with libx264 and libx265).

`ffmpeg` and `ffprobe` are used by some tests only as a reference to compare against, and those tests are skipped when they are not installed. They are never needed to use or build RayoHX.
