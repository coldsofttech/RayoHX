# CLI packaging and releasing

How the `rayohx` command is packaged and released: the `rayohx-cli` package on PyPI, plus the Linux packages built from it. The installers (the Windows setup, the zip and the Linux deb and rpm) are described in the [installer packaging notes](../../../installer/docs/packaging.md). How releases are routed for every package is in the [project releasing notes](../../../docs/releasing.md).

## What is built

| Where | What you get | Built with |
| --- | --- | --- |
| Windows, Linux or macOS with Python 3.11 or newer | the `rayohx-cli` compiled wheels on PyPI (no sdist) | `PYD_BUILD=1 uv build --wheel --package rayohx-cli` |
| Windows | the setup and a portable zip: see the [installer notes](../../../installer/docs/packaging.md) | PyInstaller and NSIS |
| Linux | `.deb` and `.rpm`, for x86_64 and arm64: see the [installer notes](../../../installer/docs/packaging.md#linux) | PyInstaller and nfpm |
| macOS | no installer: install the PyPI package | |

## The PyPI package: `rayohx-cli`

The distribution is named `rayohx-cli` and installs the `rayohx` command (`rayohx = rayohx_cli.cli:run` in `[project.scripts]`). It holds only the command line code (`rayohx_cli`), compiled into one binary (`rayohx_cli.<tag>.pyd` on Windows, `.so` elsewhere) with `.pyi` stubs beside it and no `.py` sources. `python -m rayohx_cli` does not work on the compiled build; the `rayohx` command does. Its dependencies are the core library `rayohx`, Typer, Click and Rich, so the core must be on PyPI at a compatible version before `rayohx-cli` is installable.

```bash
PYD_BUILD=1 uv build --wheel --package rayohx-cli   # dist/rayohx_cli-<version>-<tag>.whl
uvx twine check --strict dist/*        # the metadata PyPI will show
uvx --find-links dist --from dist/rayohx_cli-*.whl rayohx --version
```

The version is `__version__` in `packages/cli/src/rayohx_cli/__init__.py`; setuptools reads it from there. `packages/cli/setup.py` compiles the package with Nuitka (it needs a C compiler) when `PYD_BUILD=1`, and builds plain Python otherwise, so the installers and local development are unaffected. The `cli-build` job in `ci-cli.yml` does these steps on every change, and also checks that the wheel holds the command line and not the API or the window, so a release never meets a metadata problem for the first time.

Users install it with `uv tool install rayohx-cli` or `pipx install rayohx-cli`, and remove it with `uv tool uninstall rayohx-cli` or `pipx uninstall rayohx-cli`.

## Installers

The Windows setup (which also holds the window), the zip and the Linux packages are built by `installer/scripts/build.py`; see the [installer packaging notes](../../../installer/docs/packaging.md) for building them, the setup's behaviour, the Linux packages and signing.

## macOS

There is no installer. Install the PyPI package: `uv tool install rayohx-cli` or `pipx install rayohx-cli`.

## Checks

- The `cli-build` job in `ci-cli.yml` builds the PyPI package, checks its metadata and contents, and runs the installed wheel.
- `tests/integration/test_frozen_cli.py` starts the built program and checks it answers. It is skipped when there is no build.
- The `cli-installer` job builds the Linux packages (x86_64 and arm64) and tests them: see the [installer notes](../../../installer/docs/packaging.md#checks).

## Making a release

1. Release the core library first if the command needs a newer one: `rayohx-cli` depends on the `rayohx` package on PyPI, so that version must already be there.
2. Bump `__version__` in `packages/cli/src/rayohx_cli/__init__.py`, and move the `[Unreleased]` entries in `packages/cli/CHANGELOG.md` under a `## [x.y.z]` heading.
3. Merge that pull request, then publish a GitHub release tagged `cli-v<version>`.
4. `release.yml` calls `release-cli.yml`, which does the rest:

| Step | Result |
| --- | --- |
| Check | the tag must be `cli-v` plus the version of `rayohx-cli` |
| Build | compiled wheels of `rayohx-cli` only, one per platform and Python version |
| Installers | Linux deb and rpm (x86_64 and arm64), each smoke tested (the Windows setup is released with `installer-v<version>`) |
| Approval | the job waits for a reviewer of the `cli` environment |
| Publish | `rayohx-cli` to PyPI through trusted publishing, then the wheels, Linux packages and `SHA256SUMS.txt` to the GitHub release |

Everything is built and tested before the approval, so the reviewer approves a release that already works. Release notes are written on the GitHub release by hand (or with its "Generate release notes" button).

After the publish, the `update-latest` action moves the `cli-latest` tag and pre-release to the new version. The newest installers are under `installer-latest`, which the installer release moves in the same way.

To check a download: `sha256sum --check SHA256SUMS.txt`.

### PyPI trusted publishing

No tokens are stored. On PyPI, add a trusted publisher for the `rayohx-cli` project with the repository, the workflow `release.yml` and the environment `cli`. The environment `cli` (Settings > Environments) is also where the required reviewers are set. Check the first publish: PyPI matches the calling workflow, and a mismatch shows up as a clear error from the publish step.

### Build time

Starting targets, to be revisited after the first real runs and recorded here:

| Job | Target | `timeout-minutes` |
| --- | --- | --- |
| Package build | under 5 minutes | 10 |
| Linux packages | under 5 minutes | 15 |

A job that passes its timeout fails instead of hanging. uv caches keep builds inside the targets.

## Before the first release

- Check the installer's own list in the [installer notes](../../../installer/docs/packaging.md#before-the-first-release).
- Create the `cli` environment with its reviewers, and the trusted publisher for `rayohx-cli` on PyPI.
