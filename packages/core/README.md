# RayoHX

[![CI](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml/badge.svg)](https://github.com/coldsofttech/RayoHX/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/rayohx)](https://pypi.org/project/rayohx/)
[![Python versions](https://img.shields.io/pypi/pyversions/rayohx)](https://pypi.org/project/rayohx/)
[![Typed](https://img.shields.io/badge/typing-strict-blue)](https://mypy-lang.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![License](https://img.shields.io/github/license/coldsofttech/RayoHX)](LICENSE)

The RayoHX Python library: look at an HLS stream, choose the quality and tracks you want, and
download it to a file, all from your own code.

Want a ready-made command instead? Install the `rayohx` command line from `rayohx-cli`.

## What you can do

- Inspect a stream from its web address and see its qualities, audio and subtitle tracks and
  encryption, without downloading any media
- Choose a stream by quality, resolution or bitrate limit, and pick audio and subtitles by language
  or name
- Download in one call, with parallel segments, progress events, and cancellation that returns a
  result instead of an error
- Resume interrupted downloads where they stopped
- Save MPEG-TS and fragmented MP4 streams, join a separate audio track into one MP4 and save
  subtitles as `.vtt` files, with nothing re-encoded
- Decrypt AES-128 streams; protected (DRM) and live streams are refused with a clear explanation
- Use proxies, TLS settings, headers, cookies and a speed limit, with automatic retries
- Keep secrets such as tokens, cookies and proxy passwords out of logs and error messages

## Install

```sh
pip install rayohx
```

Requires Python 3.11 or newer. An installed FFmpeg is used only as an optional fallback for codecs
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

- [Python guide](docs/guides/python.md): inspecting, selecting, downloading, settings, events,
  errors and logging
- [Changelog](CHANGELOG.md)
- [Report a problem](https://github.com/coldsofttech/RayoHX/issues)

## License

MIT. See [LICENSE](LICENSE).
