# UI packaging

How the window's installer is built. The window is not published to PyPI: `uv build` ships only the core library and the command line, and users get the window from the Windows installer. For publishing, see the [releasing notes](../../../docs/releasing.md). The command line's own packaging is in the [CLI packaging notes](../../cli/docs/packaging.md).

## What is built

| Product | Contents | Windows | Linux |
| --- | --- | --- | --- |
| UI | `rayohxu` (window) and `rayohx` | `rayohxu-<version>-setup.exe` | none (the window needs Windows) |

macOS gets no installer.

## The pieces

```text
packages/ui/installer/   pyinstaller/ui.spec, pyinstaller/common.py, windows/ui.nsi, projectinfo.py
packages/ui/scripts/     build_installer.py   builds the window's installer
installer/windows/nsis/  common.nsh, path.ps1   the setup behavior shared with the command line
installer/tools.toml     pinned NSIS and nfpm versions
scripts/build_installer.py   shared: PyInstaller, NSIS, signing and branding
```

Names, version, icon and description are defined once: executable names come from `[project.gui-scripts]` and `[tool.installer]` in `pyproject.toml`, the version is `__version__`, and the title is `TITLE` in `rayohx_ui/app.py`. The window icon is `ui/public/icon.png` (copied into `dist` by the build).

## Building locally

```bash
uv sync --group installer
uv run python packages/ui/scripts/build_installer.py --build-frontend --smoke
```

Windows only. `--build-frontend` runs `npm ci` and `npm run build`; `--smoke` starts the built program and checks it answers. Results are in `dist/installer/` and the PyInstaller folder is in `build/installer/`. You need Node (see `.nvmrc`) and NSIS (version in `installer/tools.toml`, `makensis` on `PATH`).

## PyInstaller

`ui.spec` makes a one-folder build with `rayohx` and `rayohxu` side by side (about 69 MB). The window has no console, and the built frontend is frozen into `lib/`. The executables carry the icon and file properties taken from the project.

## Windows setup (NSIS)

`common.nsh` holds the shared behavior and `ui.nsi` what differs. It installs per user by default (`%LOCALAPPDATA%\Programs\<name>`), offers all users (administrator rights), adds Start Menu and optional desktop shortcuts, never touches `PATH`, and on uninstall removes only what setup installed.

```text
rayohxu-<version>-setup.exe  /S [/allusers | /currentuser] [/DESKTOP] [/D=C:\folder]
uninstall.exe /S [/PURGE]
```

`/D=` must come last. The product GUID in `ui.nsi` identifies it for upgrades; keep it for the life of the project.

## WebView2

The window uses the Microsoft Edge WebView2 runtime, already part of Windows 10 and 11. The installer does not add it; `cornea doctor` checks for it.

## Checks

- `tests/integration/test_frozen_ui.py` starts the built window without a window and checks it answers.
- The `ui-installer` job in `ci-ui.yml` builds the setup, then installs, runs and uninstalls it.

Windows may refuse to start a freshly built, unsigned program (error 4551); the smoke tests skip in that case.

## Making a release

1. Set `version` in `packages/ui/pyproject.toml`, and move the `[Unreleased]` entries in `packages/ui/CHANGELOG.md` under a `## [x.y.z]` heading.
2. Merge that pull request, then publish a GitHub release tagged `ui-v<version>`.
3. `release.yml` calls `release-ui.yml`, which does the rest:

| Step | Result |
| --- | --- |
| Check | the tag must be `ui-v` plus the window's version |
| Installer | the Windows setup is built and smoke tested; signed when a signing command is set |
| Approval | the job waits for a reviewer of the `ui` environment |
| Publish | the setup and `SHA256SUMS.txt` are attached to the GitHub release |

Everything is built and tested before the approval. Nothing is published to PyPI. To check a download: `Get-FileHash <file>` and compare with `SHA256SUMS.txt`.

## Signing

Signing is off by default. To turn it on, set the repository variable `SIGN_COMMAND` to a command that signs one file, with `{file}` where the path goes; `release-ui.yml` passes it to the build. The executables are signed first, then `setup.exe`. Setting it up is described in the [CLI packaging notes](../../cli/docs/packaging.md#signing).

*Placeholder:* brand artwork and winget details specific to the window.
