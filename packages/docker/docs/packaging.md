# Docker packaging and releasing

How the RayoHX image is built and published to GitHub Container Registry (GHCR). How releases are routed for every package is in the [project releasing notes](../../../docs/releasing.md). The image installs the [core](../../core/docs/packaging.md) and [command line](../../cli/docs/packaging.md) packages from source, so it does not depend on their PyPI releases.

## What is built

| Where | What you get | Built with |
| --- | --- | --- |
| Any machine with Docker | the `rayohx` image, `linux/amd64` | `docker build -f packages/docker/Dockerfile -t rayohx .` |
| A release | `ghcr.io/<owner>/<repository>`, `linux/amd64` and `linux/arm64` | `release-docker.yml` |

The image has no installer and nothing on PyPI. The image name is the repository name in lowercase.

## Building locally

Build from the repository root:

```bash
docker build -f packages/docker/Dockerfile -t rayohx .
docker build -f packages/docker/Dockerfile --build-arg VERSION=0.1.0 -t rayohx:0.1.0 .
```

| Build argument | Default | Meaning |
| --- | --- | --- |
| `PYTHON_VERSION` | `3.13` | The Python version of the base image |
| `VERSION` | `0.0.0` | Written to the `org.opencontainers.image.version` label |

## Checks on every change

`ci-docker.yml` runs from `ci.yml` for changes to the image or the packages. It builds the `amd64` image (with the GitHub Actions cache) and checks that it starts, is not root, has writable `/output` and `/workspace`, sets `RAYOHX_WORKSPACE`, and reports a failure as a short message with exit code 1 and no traceback. Nothing is published.

## Releasing to GHCR

The image is released by the tag `docker-v<version>`, for example `docker-v0.1.0`. Other packages use their own prefixes (`v`, `cli-v`, `ui-v`) and are not affected.

1. Move the `[Unreleased]` entries in `packages/docker/CHANGELOG.md` under the new version, in a pull request.
2. After it is merged, publish a GitHub release tagged `docker-v<version>`. Mark it as a pre-release if it should not become `latest`. For a full release, the workflow also moves the `docker-latest` tag and pre-release on GitHub to the new version.
3. `release.yml` sees the `docker-v` prefix and calls `release-docker.yml`, whose `docker-publish` job runs in the `docker` environment, so it waits for a reviewer's approval. It then builds both platforms with QEMU and Buildx and pushes:
   - `ghcr.io/<owner>/<repository>:<version>`
   - `ghcr.io/<owner>/<repository>:latest`, unless the release is a pre-release

   The image is built with `VERSION=<version>` and provenance attached.
4. Check it by pulling the tag and running it: `docker run --rm ghcr.io/<owner>/<repository>:<version> --version`.

Pushing uses the workflow's own `GITHUB_TOKEN` with `packages: write`, so no secret is stored.

### One-time set-up

1. Create the `docker` environment (Settings > Environments) and add the people who must approve a release as required reviewers.
2. After the first push, make the package public in the package settings if anyone should be able to pull it without signing in.

### If a release fails

- **The push was refused:** the workflow needs `packages: write`, and an existing package may need this repository added under its package settings.
- **The build fails on one platform:** reproduce with `docker buildx build --platform linux/arm64 -f packages/docker/Dockerfile .`, fix it in a pull request, and publish a new release. A pushed tag is not overwritten silently, so use a new version.
- **`latest` points at a pre-release:** pre-releases never move `latest`; if it moved, check the release was marked as a pre-release before it was published.
