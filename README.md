# RayoHX

[![CI](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml/badge.svg)](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/coldsofttech/RayoHX)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

Download HLS streams from your terminal, your Python code or a desktop window.

## What is RayoHX?

RayoHX is a tool for saving HLS streams (`.m3u8` links) as ordinary video files. Many websites play
video as a stream made of many small pieces, which is awkward to save by hand. Give RayoHX the
stream's web address and it looks at what the stream offers, lets you choose the quality, audio and
subtitles you want, and puts everything together into a single file you can keep and play anywhere.

## How it helps

- **See before you download**: check a stream's qualities, audio and subtitle tracks and encryption
  without downloading any video
- **Get exactly what you want**: pick a quality, resolution or size limit, and the audio and
  subtitles you need, instead of taking whatever comes first
- **Finish what you started**: interrupted downloads continue where they stopped
- **Safe by default**: it never replaces an existing file unless you allow it, and refuses damaged
  or unsafe streams with a clear explanation instead of failing in a confusing way
- **Use it your way**: the same features are available from the terminal, from your own Python code,
  from a container or from a desktop window

## Features

- Inspect a stream's qualities, audio and subtitle tracks and encryption
- Choose a stream by quality, resolution, bitrate limit or exact number, prefer a video codec or
  dynamic range, and pick audio and subtitles by language or name
- Fast downloads with several pieces fetched at once, a progress display and an optional speed limit
- Resume interrupted downloads, pause and continue a running one, and clean up the folders that
  interrupted downloads leave behind
- Download several streams in one go, from a list of addresses or a file
- Use a playlist file you already have instead of fetching it
- Save MPEG-TS and fragmented MP4 streams to a file, or keep the pieces as separate files in a
  folder
- Join a separate audio track into one MP4 and save subtitles as `.vtt` files, with nothing
  re-encoded
- Download encrypted (AES-128) streams, including ones whose key is stored in a local file you allow
- Clear explanation when a stream is protected (DRM) or live, as these are not supported
- Proxies (including SOCKS5 and a proxy login), client certificates, custom headers and cookies
  (including a browser's `cookies.txt`), with automatic retries
- Keep your usual options in a settings file, and check what is in effect with `rayohx config`
- Machine-readable output for scripts, including a stream of download events
- Tokens, cookies and proxy passwords are kept out of logs and error messages

## Ways to use RayoHX

| Package | What it is | Install |
|---|---|---|
| [rayohx](packages/core) | Python library | `pip install rayohx` |
| [rayohx-cli](packages/cli) | The `rayohx` command | `uv tool install rayohx-cli` |
| [rayohx-ui](packages/ui) | Desktop window (Windows) | Installer |
| [rayohx-docker](packages/docker) | The `rayohx` command as a container image | `docker pull ghcr.io/coldsofttech/rayohx` |

- **Python package**: use RayoHX inside your own programs and scripts.
- **Command line**: run `rayohx info`, `rayohx download`, `rayohx clean` and `rayohx config` from a
  terminal or a script.
- **Docker**: the same command line without installing Python, handy for servers and automation.
- **Desktop window**: work with streams from a window on Windows, no terminal needed.

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

Apache-2.0. See [LICENSE](LICENSE).
