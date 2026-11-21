# RayoHX command line

[![CI](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml/badge.svg)](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/rayohx-cli)](https://pypi.org/project/rayohx-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/rayohx-cli)](https://pypi.org/project/rayohx-cli/)
[![Typer](https://img.shields.io/badge/Typer-CLI-black)](https://typer.tiangolo.com/)
[![Rich](https://img.shields.io/badge/output-Rich-blue)](https://github.com/Textualize/rich)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![License](https://img.shields.io/github/license/coldsofttech/RayoHX)](LICENSE)

`rayohx` downloads HLS streams (`.m3u8`) to a file from your terminal.

```sh
rayohx info https://cdn.example.com/vod/master.m3u8
rayohx download https://cdn.example.com/vod/master.m3u8 -o movie.mp4
```

`info` shows what a stream offers; `download` saves it. The saved file's path is the only thing
printed on stdout, so it is easy to use in a script.

## What you can do

- See a stream's qualities, audio and subtitle tracks and encryption before downloading anything
- Choose the quality, audio and subtitles, and download to a file or a folder of segments
- Download encrypted (AES-128) streams; protected (DRM) and live streams are refused with an
  explanation
- Join a separate audio track into one MP4, with nothing re-encoded
- Continue interrupted downloads where they stopped
- Download several streams with one command, from addresses or a list file (`--input-file`)
- Use a playlist you already have, from a file, instead of fetching it (`--playlist-file`, `--base-url`)
- Follow a download from another program with `--events`
- Watch a progress bar, or get machine-readable output with `--json`
- Keep settings in a file or `RAYOHX_` environment variables
- Use `--verbose`, `--quiet`, `--no-color` and shell completion
- Download several streams at once, read local playlist files, and clean up after interrupted downloads

## Install

Requires Python 3.11 or newer. Install it in its own isolated environment:

```sh
uv tool install rayohx-cli
```

or with pipx:

```sh
pipx install rayohx-cli
```

Check it works:

```sh
rayohx --version
```

## Learn more

- [Command line guide](https://github.com/coldsofttech/RayoHX/blob/main/docs/guides/cli.md): every
  option, settings, exit codes and examples
- [Changelog](CHANGELOG.md)
- Using it from Python instead? See the [`rayohx`](https://pypi.org/project/rayohx/) library
- [Report a problem](https://github.com/coldsofttech/RayoHX/issues)

## License

Apache-2.0. See [LICENSE](LICENSE).
