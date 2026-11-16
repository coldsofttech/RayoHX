# RayoHX

[![CI](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml/badge.svg)](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/coldsofttech/RayoHX)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

Download HLS streams from your terminal, your Python code or a desktop window.

| Package | What it is | Install |
|---|---|---|
| [rayohx](packages/core) | Python library | `pip install rayohx` |
| [rayohx-cli](packages/cli) | The `rayohx` command | `uv tool install rayohx-cli` |
| [rayohxu](packages/ui) | Desktop window (Windows) | Installer |
| [rayohx-docker](packages/docker) | The `rayohx` command as a container image | `docker pull ghcr.io/coldsofttech/rayohx` |

## Quick start

```sh
rayohx info https://cdn.example.com/vod/master.m3u8
rayohx download https://cdn.example.com/vod/master.m3u8 -o movie.mp4
```

## Learn more

- [Python guide](packages/core/docs/guides/python.md)
- [Command line guide](packages/cli/docs/guides/cli.md)
- [Docker guide](packages/docker/docs/docker.md)
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Support](SUPPORT.md)

## License

MIT. See [LICENSE](LICENSE).
