# CLI packaging and releasing

How the `rayohx` command is packaged and released: the `rayohx-cli` package on PyPI, and an installer for each OS. The parts shared with the window (the build script, the NSIS behaviour in `common.nsh`, the tool versions) are described below, and how releases are routed for every package is in the [project releasing notes](../../../docs/releasing.md).

## What is built

| Where | What you get | Built with |
| --- | --- | --- |
| Any OS with Python 3.11 or newer | the `rayohx-cli` package on PyPI (wheel and sdist) | `uv build --package rayohx-cli` |
| Windows | `rayohx-<version>-setup.exe`, and a portable `…-windows-x64.zip` | PyInstaller and NSIS |
| Linux | `.deb` and `.rpm`, for x86_64 and arm64 | PyInstaller and nfpm |
| macOS | no installer: install the PyPI package | |

## The PyPI package: `rayohx-cli`

The distribution is named `rayohx-cli` and installs the `rayohx` command (`rayohx = rayohx_cli.cli:run` in `[project.scripts]`). It holds only the command line code (`rayohx_cli`). Its dependencies are the core library `rayohx`, Typer, Click and Rich, so the core must be on PyPI at a compatible version before `rayohx-cli` is installable.

```bash
uv build --package rayohx-cli          # dist/rayohx_cli-<version>.tar.gz and .whl
uvx twine check --strict dist/*        # the metadata PyPI will show
uvx --find-links dist --from dist/rayohx_cli-*.whl rayohx --version
```

The version is `__version__` in `packages/cli/src/rayohx_cli/__init__.py`; the build backend reads it from there. The `cli-build` job in `ci-cli.yml` does these steps on every change, and also checks that the wheel holds the command line and not the API or the window, so a release never meets a metadata problem for the first time.

Users install it with `uv tool install rayohx-cli` or `pipx install rayohx-cli`, and remove it with `uv tool uninstall rayohx-cli` or `pipx uninstall rayohx-cli`.

## The installer files

```text
packages/cli/installer/
  pyinstaller/cli.spec    freezes the command into a one-folder build
  pyinstaller/common.py   names, version, icon and dependencies the spec uses
  windows/cli.nsi         the Windows setup: what is specific to the command line
  linux/nfpm.yaml         the deb and rpm packages
  projectinfo.py          the names and version, read from packages/cli/pyproject.toml
```

Shared with the window and kept in the repository root: `installer/windows/nsis/common.nsh` and `path.ps1` (setup behaviour), `installer/tools.toml` (NSIS and nfpm versions) and `scripts/build_installer.py` (what the command line's and the window's build scripts share: PyInstaller, NSIS, signing and branding). `packages/cli/scripts/build_installer.py` describes the command line and runs the steps.

Names, version and description are never repeated. The executable name is the `[project.scripts]` key, the version is `__version__`, and the product title, publisher, install folder and core package are in `[tool.installer]` in `packages/cli/pyproject.toml`. The installer files read them through `projectinfo.py`, so renaming the command needs no edit in them.

## Building the installers

```bash
uv sync --group installer
uv run python packages/cli/scripts/build_installer.py --smoke                  # everything this OS can build
uv run python packages/cli/scripts/build_installer.py --format exe --smoke     # the Windows setup
uv run python packages/cli/scripts/build_installer.py --format deb,rpm --smoke # the Linux packages
```

A format the current OS cannot build (`deb` or `rpm` on Windows, `exe` on Linux) stops the build with an error. Results are in `dist/installer/` and the PyInstaller folder is in `build/installer/`. `--smoke` starts the built program and checks it answers.

| You need | For |
| --- | --- |
| `uv sync --group installer` | PyInstaller and the build backend |
| NSIS (version in `installer/tools.toml`) | the Windows setup; `makensis` on `PATH` or in `Program Files (x86)\NSIS` |
| nfpm (version in `installer/tools.toml`) | the Linux packages; set `NFPM` to run it another way, for example `NFPM="uvx nfpm"` |

### PyInstaller (Windows and Linux)

`cli.spec` makes a one-folder build (no one-file build): `rayohx` and one `lib/` folder, with none of the window's libraries (about 37 MB). The entry script is generated from the `[project.scripts]` target. On Windows the executable also carries the icon and file properties (name, version, description) taken from the project.

### Brand files

The executable, the setup and the packages use the artwork in `brand/`.

| File | Used for | Size |
| --- | --- | --- |
| `brand/light/*.ico` | the Windows executable, the setup and the uninstaller icon | 16 to 256 px |
| `brand/light/png/app-16.png` to `app-256.png` | the icon in the Linux deb and rpm (hicolor icon theme) | 16, 24, 32, 48, 64, 128, 256 px |
| `brand/dark/nsis/header.bmp` | the Windows setup header (optional) | 150x57 |
| `brand/dark/nsis/welcome.bmp` | the Windows setup welcome and finish pages (optional) | 164x314 |

Icons come from `brand/light` and the setup banners from `brand/dark`. The bitmaps must be 24-bit BMP; when one is missing, NSIS uses its default artwork.

## Windows

The installer is a setup program built with NSIS from the PyInstaller folder, plus a portable zip of the same folder. `cli.nsi` sets the product id and the program (`rayohx.exe`) and turns on the PATH option. `common.nsh` holds the rest.

- **Who it is for:** the default is a per-user install. The mode page offers all users, which asks for administrator rights.
- **Folder:** under `Program Files` (or `%LOCALAPPDATA%\Programs` for one user), from `install-dir` in `[tool.installer]`.
- **Start Menu:** a folder with a prompt where `rayohx` works, even if it was not added to `PATH`, and an uninstall shortcut.
- **PATH:** a component, on by default, edits the registry through `path.ps1` and is removed again on uninstall.
- **Uninstall:** removes only what setup installed (Settings > Apps, or `uninstall.exe`). Settings and data stay unless the user opts in.
- **Upgrades:** a newer setup with the same product id replaces the old install and clears the old `lib/` first.

Silent use, for scripts and package managers:

```text
rayohx-<version>-setup.exe /S [/allusers | /currentuser] [/NOPATH] [/D=C:\folder]
uninstall.exe /S [/PURGE]
```

`/D=` must come last. The product id (a GUID) in `cli.nsi` identifies the product for upgrades, so keep it for the life of the project. To make a new one, use `python -c "import uuid; print(uuid.uuid4())"`.

Windows may refuse to start a freshly built, unsigned program (Smart App Control or application control returns error 4551). The smoke tests skip in that case. Signing removes the problem (see [Signing](#signing)); without it, users also see SmartScreen warnings.

## Linux

`nfpm.yaml` builds one package from the PyInstaller folder, as a `.deb` and a `.rpm`, for x86_64 and arm64. It installs the folder under `/usr/lib/<name>/`, links the command into `/usr/bin`, puts the license in `/usr/share/doc/<name>/` and the icons in `/usr/share/icons/hicolor/<size>/apps/`. The only dependency is the C library (`libc6`, or `glibc` on rpm), since PyInstaller bundles the rest.

- Packages are system-wide, need root and are not signed. Removing one deletes only its own files and never touches a user's home.
- The build script sets file modes (folders 755, files 644, executables 755) before packaging.
- Values such as the name, version, architecture, description and maintainer come from the environment that `packages/cli/scripts/build_installer.py` sets from `pyproject.toml`. The maintainer needs an email in the author, which Debian expects.
- Each package is built on a runner of its own architecture, so the arm64 package is built on an arm64 runner.

| Distribution | Install | Remove |
| --- | --- | --- |
| Debian, Ubuntu | `sudo apt install ./rayohx_<version>_amd64.deb` (or `_arm64.deb` on ARM) | `sudo apt remove rayohx` |
| Fedora, RHEL | `sudo dnf install ./rayohx-<version>-1.x86_64.rpm` (or `.aarch64.rpm` on ARM) | `sudo dnf remove rayohx` |

## macOS

There is no installer. Install the PyPI package: `uv tool install rayohx-cli` or `pipx install rayohx-cli`.

## Checks

- The `cli-build` job in `ci-cli.yml` builds the PyPI package, checks its metadata and contents, and runs the installed wheel.
- `tests/integration/test_frozen_cli.py` starts the built program and checks it answers. It is skipped when there is no build.
- The `cli-installer` job builds the installer on Windows and on Linux (x86_64 and arm64), starts the frozen program, then installs it, runs it and removes it again. On Windows that is the per-user setup, the `PATH` entry and the uninstaller. On Linux it is the deb with `apt` and the rpm in a Fedora container, including the icon.

## Making a release

1. Release the core library first if the command needs a newer one: `rayohx-cli` depends on the `rayohx` package on PyPI, so that version must already be there.
2. Bump `__version__` in `packages/cli/src/rayohx_cli/__init__.py`, and move the `[Unreleased]` entries in `packages/cli/CHANGELOG.md` under a `## [x.y.z]` heading.
3. Merge that pull request, then publish a GitHub release tagged `cli-v<version>`.
4. `release.yml` calls `release-cli.yml`, which does the rest:

| Step | Result |
| --- | --- |
| Check | the tag must be `cli-v` plus the version of `rayohx-cli` |
| Build | wheel and sdist of `rayohx-cli` only |
| Installers | Windows setup and zip, Linux deb and rpm (x86_64 and arm64), each smoke tested; signed when a signing command is set |
| Approval | the job waits for a reviewer of the `cli` environment |
| Publish | `rayohx-cli` to PyPI through trusted publishing, then the wheel, sdist, installers and `SHA256SUMS.txt` to the GitHub release |

Everything is built and tested before the approval, so the reviewer approves a release that already works. Release notes are written on the GitHub release by hand (or with its "Generate release notes" button).

To check a download: `sha256sum --check SHA256SUMS.txt` (Linux), or `Get-FileHash <file>` on Windows and compare with the list.

### PyPI trusted publishing

No tokens are stored. On PyPI, add a trusted publisher for the `rayohx-cli` project with the repository, the workflow `release.yml` and the environment `cli`. The environment `cli` (Settings > Environments) is also where the required reviewers are set. Check the first publish: PyPI matches the calling workflow, and a mismatch shows up as a clear error from the publish step.

### Build time

Starting targets, to be revisited after the first real runs and recorded here:

| Job | Target | `timeout-minutes` |
| --- | --- | --- |
| Package build | under 5 minutes | 10 |
| Windows installer | under 10 minutes | 30 |
| Linux packages | under 5 minutes | 15 |

A job that passes its timeout fails instead of hanging. uv caches keep builds inside the targets.

## Signing

Signing is off by default. It applies to the Windows programs only; Linux packages are not signed and the PyPI package is protected by trusted publishing.

To turn it on, set the repository variable `SIGN_COMMAND` to a command that signs one file, with `{file}` where the path goes. The build signs the executables first, then the `setup.exe`, so the files inside the installer are signed too. Any provider works, since the command is yours. Examples of what exists, without a recommendation:

- SignPath (free for qualifying open-source projects)
- Azure Trusted Signing (paid subscription)
- a certificate from a certificate authority, on a hardware token or in a cloud HSM

Secrets the command needs (a token, a certificate password) are added as repository secrets and passed to the step that builds the installer through `env` in `release-cli.yml`, which is the one place to edit.

## Package managers

Homebrew, Scoop and winget are not updated by the workflows for now.

## Before the first release

- Check that the product id (GUID) in `packages/cli/installer/windows/cli.nsi` is the one you want to keep for good.
- Pin the NSIS and nfpm versions in `installer/tools.toml`, and check the `choco` version exists.
- Add an email to the author in `packages/cli/pyproject.toml`, which Debian expects in the maintainer field.
- Create the `cli` environment with its reviewers, and the trusted publisher for `rayohx-cli` on PyPI.
- Decide on signing.
