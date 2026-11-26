# Core packaging and releasing

How the `rayohx` library is packaged and released to PyPI. The command line, Docker image, desktop window and installers are released from their own repositories.

## What is built

| Where | What you get | Built with |
| --- | --- | --- |
| Windows, Linux or macOS with Python 3.11 or newer | the `rayohx` compiled wheels on PyPI (no sdist) | `PYD_BUILD=1 uv build --wheel --package rayohx` |

The core has no installer. The command line and the desktop window ship their own, and carry their own copy of the library.

## The PyPI package: `rayohx`

The distribution is named `rayohx` and holds only the library, compiled into one binary (`rayohx.<tag>.pyd` on Windows, `rayohx.<tag>.so` elsewhere) with a `rayohx/` folder of `.pyi` type stubs and a `py.typed` marker beside it. The stub folder has no `__init__.py`, so Python loads the binary. It has no command and no extras. Its dependencies are `httpx` and `cryptography`, and it supports Python 3.11 to 3.15.

```bash
PYD_BUILD=1 uv build --wheel --package rayohx   # dist/rayohx-<version>-<tag>.whl
uvx twine check --strict dist/*      # the metadata PyPI will show
```

The build backend is setuptools. With `PYD_BUILD=1`, `packages/core/setup.py` compiles `src/rayohx` with Nuitka (it needs a C compiler) and generates the stubs with mypy's `stubgen`; without it the package builds as plain Python. The name comes from `packages/core/pyproject.toml`, and the version is read from `__version__` in `packages/core/src/rayohx/__init__.py`. The description on PyPI is `packages/core/README.md`. Nuitka supports Python 3.15 only experimentally (as of 4.3.5).

The `core-build` job in `ci.yml` runs these steps on every change, and also checks that the wheel holds the binary and stubs but no `.py` sources, and not the test plugin, so a release never meets a metadata problem for the first time.

Users install it with `pip install rayohx` or `uv add rayohx`.

## Releasing to PyPI

Publishing a GitHub release runs `release.yml`, and the tag decides what is released:

| Tag | Releases | Environment |
| --- | --- | --- |
| `v<version>` | the library, `rayohx`, on PyPI as compiled wheels (no sources) | `core` |

The tag must equal the package version, for example `v0.1.0`. The pytest plugin is not released: other repositories install it from git at a `pytest-v<version>` tag (see its [README](../packages/pytest/README.md)). Release the core before the command line, because `rayohx-cli` depends on this package being on PyPI.

1. Bump `__version__` in `packages/core/src/rayohx/__init__.py` and move the `[Unreleased]` entries in the root `CHANGELOG.md` under the new version, in a pull request.
2. After it is merged, publish a GitHub release tagged `v<version>`.
3. `release.yml` sees the `v` prefix and runs three jobs:
   - **`core-check`** checks the tag equals the package version (it fails if they differ). **`core-build`** then builds one wheel per OS, architecture and Python version with cibuildwheel, runs the unit tests against each, and uploads the files.
   - **`core-publish`** runs in the `core` environment, so it waits for a reviewer's approval. It publishes the files to PyPI, then attaches them and a `SHA256SUMS.txt` to the GitHub release.
4. Check the new version on PyPI and install it in a clean environment: `uv run --with rayohx==<version> python -c "import rayohx; print(rayohx.__version__)"`.

Publishing uses [trusted publishing](https://docs.pypi.org/trusted-publishers/), so no API token is stored, and only the publish job gets the `id-token` permission.

### One-time set-up

1. On PyPI, add a trusted publisher for the `rayohx` project: this repository, workflow `release.yml` and environment `core`.
2. Create the `core` environment (Settings > Environments) and add the people who must approve a release as required reviewers.

### If a release fails

- **The tag does not match** the version: delete the release and the tag, fix the version in a pull request, and publish again.
- **Publishing was refused:** the trusted publisher on PyPI does not match the workflow or environment above.
- **PyPI never accepts a version twice**, even after deleting it. If a version went out wrong, fix it and release the next one.
