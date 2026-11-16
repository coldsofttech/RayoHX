# RayoHX Docker

[![CI](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml/badge.svg)](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/coldsofttech/RayoHX)](LICENSE)

The `rayohx` command as a small container image, for servers and pipelines.

```sh
docker run --rm -v "$PWD/downloads:/output" ghcr.io/coldsofttech/rayohx download https://example.com/master.m3u8 -o /output/movie.mp4
```

The image runs as a normal user, supports `linux/amd64` and `linux/arm64`, and keeps its downloads and resume state in folders you can mount. See the [Docker guide](docs/docker.md).
