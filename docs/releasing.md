# Releasing

How a release is routed. Each package's packaging notes hold the steps, signing and set-up for its own release: [core](../packages/core/docs/packaging.md#releasing-to-pypi), [CLI](../packages/cli/docs/packaging.md#making-a-release), [UI](../packages/ui/docs/packaging.md#making-a-release) and [Docker](../packages/docker/docs/packaging.md#releasing-to-ghcr).

## Releases are routed by tag

Publishing a GitHub release runs `release.yml`, and the tag decides what is released. Each part has its own workflow, its own version and its own approval: the job that publishes waits for a reviewer of its environment (Settings > Environments), after everything has been built and tested.

| Tag | Releases | Environment |
| --- | --- | --- |
| `v<version>` | the core library, `rayohx`, on PyPI | `core` |
| `cli-v<version>` | the command line, `rayohx-cli`, on PyPI, and its Windows and Linux installers | `cli` |
| `installer-v<version>` | the full Windows setup (command line and window) and the portable zip; version in `installer/build.toml` | `installer` |
| `docker-v<version>` | the Docker image on GHCR | `docker` |

The tag must equal the version of the package it releases. Release the core before the command line, because `rayohx-cli` depends on the `rayohx` package on PyPI. Every release that attaches files also gets `SHA256SUMS.txt`.

Before releasing, bump the package's version and move its `[Unreleased]` changelog entries under a version heading.
