# RayoHX API

[![CI](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml/badge.svg)](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/rayohx-api)](https://pypi.org/project/rayohx-api/)
[![Python versions](https://img.shields.io/pypi/pyversions/rayohx-api)](https://pypi.org/project/rayohx-api/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688)](https://fastapi.tiangolo.com/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![License](https://img.shields.io/github/license/coldsofttech/RayoHX)](LICENSE)

`rayohx-api` runs RayoHX as a web service, so other apps can work with HLS streams (`.m3u8`) over HTTP.

```sh
RAYOHX_API_API_KEYS='["my-secret-key"]' rayohx-api
```

The service listens on `http://127.0.0.1:8000`, and its interactive documentation is served by the running service.

## What you can do

- Look at a stream over HTTP
- Protect the service with API keys, or turn authentication off for local development
- Check that the service is running with the health endpoint
- Get JSON logs and consistent error responses
- Configure everything with `RAYOHX_API_` environment variables or a `.env` file

## Install

Requires Python 3.11 or newer. Install it in its own isolated environment:

```sh
uv tool install rayohx-api
```

or with pipx:

```sh
pipx install rayohx-api
```

## Settings

| Variable | Default | What it does |
| --- | --- | --- |
| `RAYOHX_API_HOST` | `127.0.0.1` | Address to listen on |
| `RAYOHX_API_PORT` | `8000` | Port to listen on |
| `RAYOHX_API_API_KEYS` | none | Accepted API keys (required unless authentication is off) |
| `RAYOHX_API_AUTH_MODE` | keys | Set to `none` to disable authentication for local development |

## Learn more

- [Changelog](CHANGELOG.md)
- Using it from Python instead? See the [`rayohx`](https://pypi.org/project/rayohx/) library
- [Report a problem](https://github.com/coldsofttech/RayoHX/issues)

## License

MIT. See [LICENSE](LICENSE).
