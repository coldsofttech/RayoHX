# RayoHX API

[![CI](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml/badge.svg)](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688)](https://fastapi.tiangolo.com/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![License](https://img.shields.io/github/license/coldsofttech/RayoHX)](LICENSE)

`rayohx-api` runs RayoHX as a web service that other apps can call over HTTP. It is built into the RayoHX desktop app, so there is nothing to install on its own and it is not published as a separate package.

To run it by itself, from a checkout of the repository:

```sh
RAYOHX_API_API_KEYS='["my-secret-key"]' uv run rayohx-api
```

The service listens on `http://127.0.0.1:8000`. Its interactive documentation is switched off unless you set `RAYOHX_API_DOCS_ENABLED=true`.

## What you can do

- Protect the service with API keys, or turn authentication off for local development
- Inspect a playlist, or start one or many downloads with every engine option (network, selection, storage and output settings)
- Check that the service is running with the health and readiness endpoints
- Get JSON logs and consistent error responses
- Configure everything with `RAYOHX_API_` environment variables or a `.env` file

## Settings

| Variable | Default | What it does |
| --- | --- | --- |
| `RAYOHX_API_HOST` | `127.0.0.1` | Address to listen on |
| `RAYOHX_API_PORT` | `8000` | Port to listen on |
| `RAYOHX_API_API_KEYS` | none | Accepted API keys (required unless authentication is off) |
| `RAYOHX_API_AUTH_MODE` | keys | Set to `none` to disable authentication for local development |

The full list of settings is in the [API guide](docs/api.md).

## Learn more

- [API guide](docs/api.md): running it, every setting, the endpoints and the OpenAPI contract
- [Security](docs/security.md): how requests are protected
- [Architecture](docs/architecture.md) and [development](docs/development.md): how it is built and how to work on it
- [Changelog](CHANGELOG.md)
- Using RayoHX from Python instead? See the [`rayohx`](../core) library
- [Report a problem](https://github.com/coldsofttech/RayoHX/issues)

## License

Apache-2.0. See [LICENSE](LICENSE).
