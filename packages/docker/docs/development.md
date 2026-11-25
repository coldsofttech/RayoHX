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

## Tests

The image has its own pytest suite in `packages/docker/tests`. It drives the `docker` command, so Docker must be running; without it the tests skip. It checks that the command runs, the image runs as a non-root user, `/output` and `/workspace` are writable, `RAYOHX_WORKSPACE` is set, a failure is a short `Error:` message without a traceback, FFmpeg and pip are absent, and the labels, entrypoint and volumes are right.

```bash
uv run --with pytest pytest -c packages/docker/pytest.ini packages/docker/tests      # builds rayohx:test first
RAYOHX_IMAGE=rayohx pytest -c packages/docker/pytest.ini packages/docker/tests       # test an image you already built
docker image ls rayohx --format '{{.Size}}'                                          # keep an eye on the size
```

CI (`ci-docker.yml`) builds the image and runs the same suite against it. The `-c` option keeps the repository's coverage settings from applying. Behaviour changes to the command itself belong in [packages/cli](../../cli/docs/development.md), not here.

### Smoke test the image

`scripts/smoke/` builds the image from the repository root and tries it. It is a manual check,
separate from the pytest suite, and it needs Docker and network access. The scripts are
PowerShell. The image installs the packages as plain Python on Linux, so there is no `.pyd` here.

```powershell
./scripts/smoke/setup_image.ps1   # builds rayohx:local-test
./scripts/smoke/test_image.ps1    # shows the user the container runs as, then runs `rayohx info`
```

`test_image.ps1` prints the container's `id` output, so you can see by eye that it is not uid 0; it
does not fail on it. It then runs `rayohx info` on the **first line** of `scripts/smoke/test_links.txt`
and fails if the command exits with an error. To try another stream, put its URL on the first line
of that file; any further lines are ignored. `test_links.txt` is kept in the repository, so use a
stream you are allowed to share.

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
