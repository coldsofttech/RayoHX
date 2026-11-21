# Core packaging and releasing

How the `rayohx` library is packaged and released to PyPI. How releases are routed for every package is in the [project releasing notes](../../../docs/releasing.md); the command line, which depends on this package, is in [CLI packaging and releasing](../../cli/docs/packaging.md).

## What is built

| Where | What you get | Built with |
| --- | --- | --- |
| Any OS with Python 3.11 or newer | the `rayohx` package on PyPI (wheel and sdist) | `uv build --package rayohx` |

The core has no installer. The command line and the window ship their own, and carry their own copy of the library.

## The PyPI package: `rayohx`

The distribution is named `rayohx` and holds only the library (`rayohx`, with its `py.typed` marker). It has no command and no extras. Its dependencies are `httpx` and `cryptography`, and it supports Python 3.11 to 3.15.

```bash
uv build --package rayohx            # dist/rayohx-<version>.tar.gz and .whl
uvx twine check --strict dist/*      # the metadata PyPI will show
```

The build backend is Hatchling. The wheel is built from `src/rayohx`, the name and version come from `packages/core/pyproject.toml`, and the version is read from `__version__` in `packages/core/src/rayohx/__init__.py`. The description on PyPI is `packages/core/README.md`.

The `core-build` job in `ci-core.yml` runs these steps on every change, and also checks that the wheel holds the core library and not the command line, the API or the window, so a release never meets a metadata problem for the first time.

Users install it with `pip install rayohx` or `uv add rayohx`.

## Releasing to PyPI

The core is released by the tag `v<version>`, for example `v0.1.0`. Other packages use their own prefixes (`cli-v`, `ui-v`, `docker-v`) and are not affected. Release the core before the command line, because `rayohx-cli` depends on this package being on PyPI.

1. Bump `__version__` in `packages/core/src/rayohx/__init__.py` and move the `[Unreleased]` entries in `packages/core/CHANGELOG.md` under the new version, in a pull request.
2. After it is merged, publish a GitHub release tagged `v<version>`.
3. `release.yml` sees the `v` prefix and calls `release-core.yml`, which has two jobs:
   - **`core-build`** checks the tag equals the package version (it fails if they differ), builds the wheel and sdist, runs `twine check --strict`, and uploads the files.
   - **`core-publish`** runs in the `core` environment, so it waits for a reviewer's approval. It publishes the files to PyPI, then attaches them and a `SHA256SUMS.txt` to the GitHub release.
4. Check the new version on PyPI and install it in a clean environment: `uv run --with rayohx==<version> python -c "import rayohx; print(rayohx.__version__)"`.

Publishing uses [trusted publishing](https://docs.pypi.org/trusted-publishers/), so no API token is stored, and only the publish job gets the `id-token` permission.

### One-time set-up

1. On PyPI, add a trusted publisher for the `rayohx` project: this repository, workflow `release.yml` and environment `core`. The workflow is the one that starts the release, not `release-core.yml`, which it calls.
2. Create the `core` environment (Settings > Environments) and add the people who must approve a release as required reviewers.

### If a release fails

- **The tag does not match** the version: delete the release and the tag, fix the version in a pull request, and publish again.
- **Publishing was refused:** the trusted publisher on PyPI does not match the workflow or environment above.
- **PyPI never accepts a version twice**, even after deleting it. If a version went out wrong, fix it and release the next one.
