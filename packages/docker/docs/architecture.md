# Docker architecture

How the RayoHX image is put together. For running it, see the [Docker guide](docker.md); for working on it, see [development](development.md).

## What the image is

The image runs the same `rayohx` command as the Python package. It holds no second downloader: it installs the `rayohx` library and the `rayohx_cli` command line from this repository, so the image, the PyPI packages and the installers behave the same way. See the [CLI architecture](../../cli/docs/architecture.md) and the [core architecture](../../core/docs/architecture.md) for how the command works inside.

## Files

```text
packages/docker/
  Dockerfile                the two-stage build
  Dockerfile.dockerignore   keeps the build context to the packages the image needs
  docs/                     this documentation
  CHANGELOG.md             changes to the image
  README.md                 the image for users
```

The build context is the repository root, so both packages are available to `COPY`.

## Stages

| Stage | Purpose |
| --- | --- |
| `build` | A slim Python image where the packages and their dependencies are installed into a virtual environment at `/opt/venv`. pip is removed from the environment afterwards. |
| `runtime` | The same slim base with only `/opt/venv` copied in: no compilers, no pip and no sources. |

Splitting the stages keeps the final image small and keeps build tools out of it. The Python version is the `PYTHON_VERSION` build argument (default 3.13), and both stages use the same one so the virtual environment matches its interpreter.

## The runtime image

- **User.** A fixed system user and group `rayohx` (uid and gid `10001`) with no home folder and no login shell, so files written to a mounted folder have a predictable owner.
- **Folders.** `/output` is the working directory and `/workspace` holds partial downloads and resume state (`RAYOHX_WORKSPACE`). Both are declared as volumes and owned by `rayohx`.
- **Entry point.** `ENTRYPOINT ["rayohx"]` with `CMD ["--help"]`, so everything after the image name is a normal command.
- **Environment.** `RAYOHX_WORKSPACE=/workspace` and `NO_COLOR=1` are set. Python output is unbuffered and no bytecode is written. Command line options win over `RAYOHX_` variables.
- **Labels.** The OCI labels (title, description, source, license and `VERSION`) are set so registries show the right details.

## No FFmpeg

Joining audio and video is built into the library, so FFmpeg is not installed. That keeps the image small and removes a large source of vulnerabilities. Someone who needs FFmpeg for an unusual codec builds their own image on top of this one.

## Platforms and releases

The image is built for `linux/amd64` and `linux/arm64`. CI builds `amd64` only and checks it; a `docker-v<version>` release builds both and pushes to GHCR. See [packaging and releasing](packaging.md).
