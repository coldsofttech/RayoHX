# RayoHX

[![CI](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml/badge.svg)](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/rayohx)](https://pypi.org/project/rayohx/)
[![Python versions](https://img.shields.io/pypi/pyversions/rayohx)](https://pypi.org/project/rayohx/)
[![Typed](https://img.shields.io/badge/typing-strict-blue)](https://mypy-lang.org/)
[![httpx](https://img.shields.io/badge/HTTP-httpx-blue)](https://www.python-httpx.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![License](https://img.shields.io/github/license/coldsofttech/RayoHX)](LICENSE)

The RayoHX Python library: look at an HLS stream, choose the quality and tracks you want, and
download it to a file, all from your own code.

Coming from `pym3u8downloader`? See the
[migration guide](https://github.com/coldsofttech/RayoHX/blob/main/docs/guides/migration.md).

Want a ready-made command instead? Install the `rayohx` command line from `rayohx-cli`.

## What you can do

- Inspect a stream from its web address and see its qualities, audio and subtitle tracks and
  encryption, without downloading any media
- Choose a stream by quality, resolution or bitrate limit, or exactly by its number, resolution or
  name, prefer a video codec or dynamic range, and pick audio and subtitles by language or name
- Download in one call, with parallel segments, progress events, and cancellation that returns a
  result instead of an error
- Pause a running download and resume it later
- Work with a playlist you already have as text, without fetching it
- Download several streams one after another into a folder with `download_many`
- Find and remove the working folders that interrupted downloads leave behind
- Resume interrupted downloads where they stopped, with disk space needed for the video only
- Save segments as separate files in a folder, or download just the video of a stream with a
  separate audio track
- Save MPEG-TS and fragmented MP4 streams, join a separate audio track into one MP4 and save
  subtitles as `.vtt` files, with nothing re-encoded
- Decrypt AES-128 streams, including keys given in the playlist or supplied by your own code; protected (DRM) and live streams are refused with a clear explanation
- Use proxies (including SOCKS5 and ones from the environment), client certificates, TLS settings,
  headers, cookies and a speed limit, with automatic retries
- Refuse damaged or hostile streams with a clear error instead of crashing, and never replace an
  existing file unless you allow it
- Keep secrets such as tokens, cookies and proxy passwords out of logs and error messages

## Install

```sh
pip install rayohx
```

Requires Python 3.11 or newer on Windows, Linux or macOS, where a ready-to-use compiled build is installed for your platform. An installed FFmpeg is used only as an optional fallback for codecs
the built-in remuxer cannot copy.

## Quick start

```python
import rayohx

url = "https://cdn.example.com/vod/master.m3u8"

playlist = rayohx.inspect(url)
for variant in playlist.variants:
    print(variant.height, variant.bandwidth)

result = rayohx.download(url, "video.ts", quality="720p")
print(result.output.path, result.output.size_bytes)
```

## Learn more

- [Python guide](https://github.com/coldsofttech/RayoHX/blob/main/docs/guides/python.md): inspecting, selecting, downloading, settings, events,
  errors and logging
- [Migration guide](https://github.com/coldsofttech/RayoHX/blob/main/docs/guides/migration.md):
  moving from `pym3u8downloader`
- Prefer a command? See the [`rayohx-cli`](https://pypi.org/project/rayohx-cli/) command line
- [Changelog](CHANGELOG.md)
- [Report a problem](https://github.com/coldsofttech/RayoHX/issues)

## License

Apache-2.0. See [LICENSE](LICENSE).
