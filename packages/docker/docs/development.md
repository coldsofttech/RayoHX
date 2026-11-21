# Docker development

How to work on `packages/docker`. For how the image is built, see [architecture](architecture.md); for running it, see the [Docker guide](docker.md). General set-up for the whole repository is in the [project development notes](../../../docs/development.md).

## Build and run

Build from the repository root, so both packages are in the build context:

```bash
docker build -f packages/docker/Dockerfile -t rayohx .
docker build -f packages/docker/Dockerfile --build-arg PYTHON_VERSION=3.12 -t rayohx:py312 .

docker run --rm rayohx --version
docker run --rm rayohx info https://example.com/master.m3u8
```

## Checks

CI (`ci-docker.yml`) builds the image and runs the same checks you can run by hand:

```bash
docker run --rm rayohx --version
docker run --rm rayohx download --help > /dev/null
docker run --rm --entrypoint id rayohx -u                                 # must not be 0
docker run --rm --entrypoint sh rayohx -c 'touch /output/x /workspace/x'  # folders are writable
docker run --rm --entrypoint printenv rayohx RAYOHX_WORKSPACE             # /workspace
docker run --rm rayohx info http://127.0.0.1:1/none.m3u8 --retries 0      # exit 1, "Error:", no traceback
docker image ls rayohx --format '{{.Size}}'                               # keep an eye on the size
```

There is no unit test suite for this package: the image runs the command line, which is tested in [packages/cli](../../cli/docs/development.md). Behaviour changes belong there, not here.

## Rules to keep

- **One downloader.** Do not add a second implementation to the image. If the image needs something the command does not do, change the command.
- **Stay non-root.** The runtime stage must end with `USER rayohx`, and the image must not run as uid 0.
- **Keep it small.** No compilers, pip, package caches or FFmpeg in the runtime stage. Add a package only with a reason in the comment.
- **No secrets in the image.** Never put headers, cookies, tokens or credentials in a `Dockerfile`, build argument or `ENV`. Users pass them at run time (see [security](security.md)).
- **Keep the build context small.** Add new files the build needs to `Dockerfile.dockerignore`, and leave the rest out.
- **Explain exceptions.** A `# nosemgrep` or Trivy ignore needs a reason in a comment.

## Changing the image

1. Edit `Dockerfile`, keeping the two stages and the comments at the top current.
2. Build it and run the checks above, on both `amd64` and, if you changed the base or added a package, `arm64` (`docker buildx build --platform linux/arm64`).
3. If the change is visible to users (a folder, variable, user or tag), update the [Docker guide](docker.md), `README.md` and the `[Unreleased]` section of `packages/docker/CHANGELOG.md`.
