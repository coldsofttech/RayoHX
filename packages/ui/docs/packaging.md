# UI packaging

How the window is packaged. The window is not published to PyPI: `uv build` ships only the core library and the command line, and users get the window from the Windows installer. The installer is shared with the command line: one setup, `rayohx-<version>-full-setup.exe`, installs the command line, the window or both. How it is built, how it behaves and how it is released is in the [installer packaging notes](../../../installer/docs/packaging.md). How releases are routed for every package is in the [project releasing notes](../../../docs/releasing.md).

## What the window contributes

- The executable `rayohxu` (no console), named by `[project.gui-scripts]` in `pyproject.toml`. The version is `version` there, and the title is `TITLE` in `rayohx_ui/app.py`.
- The built frontend (`rayohx_ui/ui/dist`), frozen into the installer's `lib/` folder. Build it first with `npm ci && npm run build` in `packages/ui/src/rayohx_ui/ui`, or run the installer build with `--build-frontend`.
- The window icon, `ui/public/icon.png` (copied into `dist` by the build).
- A `[tool.installer]` section in `pyproject.toml`, read by the `Ui` class in `installer/scripts/build.py`.

`Ui.dependencies()` in `installer/scripts/build.py` lists the window's dependencies for the build.

## WebView2

The window uses the Microsoft Edge WebView2 runtime, already part of Windows 10 and 11. The installer does not add it; `cornea doctor` checks for it.

## Checks

- `tests/integration/test_frozen_ui.py` starts the built window without a window and checks it answers. It is skipped when there is no build (`uv run python installer/scripts/build.py --build-frontend`).
- The `ui-installer` job in `ci-ui.yml` builds the full setup, then installs, runs and uninstalls it: see the [installer notes](../../../installer/docs/packaging.md#checks).

## The compiled wheel

The window's Python package can also be built as a compiled wheel, which the `ui-build` job in `ci-ui.yml` checks on every change: `PYD_BUILD=1 uv build --wheel --package rayohx-ui`. `setup.py` compiles `rayohx_ui` with Nuitka (it needs a C compiler) into one binary (`rayohx_ui.<tag>.pyd` on Windows, `.so` elsewhere). Beside it, a `rayohx_ui/` folder holds the `.pyi` stubs and, in `assets/`, the built frontend (`ui/dist`) when it has been built. The window looks for `assets/` first and falls back to `ui/dist`, so source checkouts and the installer are unchanged. `python -m rayohx_ui` does not work on the compiled build; the `rayohxu` command does. Nuitka supports Python 3.15 only experimentally (as of 4.3.5). The wheel is not published; the installer still freezes the plain sources.

## Making a release

The window has no release of its own. Set `version` in `packages/ui/pyproject.toml` and move the `[Unreleased]` entries in `packages/ui/CHANGELOG.md` under a `## [x.y.z]` heading, then ship it in a new setup version: see [Making a release](../../../installer/docs/packaging.md#making-a-release) in the installer notes. The newest setup is always under the `installer-latest` pre-release on GitHub, which the installer release moves after each full release.
