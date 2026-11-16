# RayoHX desktop window

[![CI](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml/badge.svg)](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/rayohxu)](https://pypi.org/project/rayohxu/)
[![React](https://img.shields.io/badge/React-UI-61dafb)](https://react.dev/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![License](https://img.shields.io/github/license/coldsofttech/RayoHX)](LICENSE)

`rayohx-ui` opens RayoHX in its own desktop window, so you can work with HLS streams (`.m3u8`) without the terminal.

```sh
rayohx-ui
```

## What you can do

- Use RayoHX from a native window instead of the command line
- Nothing else to run: the HTTP API is built in and starts with the window
- Open links and pick files and folders with the usual system dialogs

## Install

Requires Windows and Python 3.11 or newer. Install it in its own isolated environment:

```sh
uv tool install rayohxu
```

or with pipx:

```sh
pipx install rayohxu
```

Then start it with `rayohx-ui`.

## Learn more

- [Changelog](CHANGELOG.md)
- Prefer the terminal? See the [`rayohx-cli`](https://pypi.org/project/rayohx-cli/) command line
- Using it from Python instead? See the [`rayohx`](https://pypi.org/project/rayohx/) library
- [Report a problem](https://github.com/coldsofttech/RayoHX/issues)

## License

MIT. See [LICENSE](LICENSE).
