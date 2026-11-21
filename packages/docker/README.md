# RayoHX Docker

[![CI](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml/badge.svg)](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml)
[![Security](https://github.com/coldsofttech/RayoHX/actions/workflows/security.yml/badge.svg)](https://github.com/coldsofttech/RayoHX/actions/workflows/security.yml)
[![GHCR](https://img.shields.io/badge/ghcr.io-coldsofttech%2Frayohx-blue?logo=docker&logoColor=white)](https://github.com/coldsofttech/RayoHX/pkgs/container/rayohx)
[![Platforms](https://img.shields.io/badge/platforms-linux%2Famd64%20%7C%20linux%2Farm64-blue)](docs/docker.md)
[![Non-root](https://img.shields.io/badge/runs%20as-non--root-green)](docs/security.md)
[![Python](https://img.shields.io/badge/base-python%3Aslim-blue?logo=python&logoColor=white)](docs/architecture.md)
[![License](https://img.shields.io/github/license/coldsofttech/RayoHX)](LICENSE)

The `rayohx` command as a small container image, for servers and pipelines. It downloads HLS
streams (`.m3u8`) to a file, with nothing to install except Docker.

```sh
docker run --rm -v "$PWD/downloads:/output" ghcr.io/coldsofttech/rayohx download https://example.com/master.m3u8 -o /output/movie.mp4
```

It is the same `rayohx` command as the Python package, so everything after the image name works
as it does in a terminal.

## What you can do

- See a stream's qualities, audio and subtitle tracks and encryption before downloading anything
- Choose the quality, audio and subtitles, and save to a file or a folder of segments
- Join separate audio and video into one MP4 without installing FFmpeg
- Continue interrupted downloads by keeping the resume folder between runs
- Get machine-readable output with `--json`, and set any option with a `RAYOHX_` variable
- Read headers and cookies from a mounted file, so secrets stay out of your shell history

## Run it

Look at a stream without downloading it:

```sh
docker run --rm ghcr.io/coldsofttech/rayohx info https://example.com/master.m3u8
```

Download it, keeping the file and the resume state:

```sh
docker run --rm \
  -v "$PWD/downloads:/output" \
  -v rayohx-work:/workspace \
  ghcr.io/coldsofttech/rayohx download https://example.com/master.m3u8 -o /output/movie.mp4
```

| Folder | Purpose |
| --- | --- |
| `/output` | Where files are saved. Mount a folder to keep them. |
| `/workspace` | Where partial downloads are kept. Mount a folder or a named volume to resume later. |

The image runs as a normal user (uid `10001`), supports `linux/amd64` and `linux/arm64`, and
carries no FFmpeg, compilers or pip.

## Learn more

- [Docker guide](docs/docker.md): folders, settings, exit codes, building and publishing
- [Command line guide](https://github.com/coldsofttech/RayoHX/blob/main/packages/cli/docs/guides/cli.md):
  every option and example
- [Security](docs/security.md): handling secrets and running the container safely
- [Changelog](CHANGELOG.md)
- Using it from Python instead? See the [`rayohx`](https://pypi.org/project/rayohx/) library
- [Report a problem](https://github.com/coldsofttech/RayoHX/issues)

## License

Apache-2.0. See [LICENSE](LICENSE).
