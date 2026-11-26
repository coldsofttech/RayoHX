# Python guide

Everything RayoHX does is available as plain Python. The library never prints, never exits the
process and never reads global state: it takes typed settings, returns frozen results and raises
meaningful exceptions. The command line, the API and the desktop window are thin front ends over
the same package; they live in [their own repositories](../../README.md#other-ways-to-use-rayohx).

```python
import rayohx
from rayohx.config import SelectionConfig

playlist = rayohx.inspect("https://cdn.example.com/vod/master.m3u8")

for variant in playlist.variants:
    print(variant.height, variant.bandwidth, variant.uri)

choice = rayohx.select_stream(playlist, SelectionConfig(quality="720p", audio_languages=("en",)))
print(choice.variant.uri)
print([track.name for track in choice.audio_tracks])
print(choice.notes)  # why a wish could not be met, if any
```

To download it:

```python
result = rayohx.download("https://cdn.example.com/vod/master.m3u8", "video.ts", quality="720p")
print(result.output.path, result.output.size_bytes)
```

> **What works today.** You can look at a stream without downloading it, parse playlists, choose
> tracks, and download MPEG-TS and fragmented MP4 streams (including AES-128 encrypted ones) to a
> file or a folder of segments, with events, cancellation and resume. Streams that need merging or
> remuxing are not supported yet. See [Not yet available](#not-yet-available).

## Contents

| Page | What it covers |
|---|---|
| [Inspecting streams](python/inspecting.md) | `inspect`, `inspect_playlist`, `inspect_text`, `parse_playlist`, `is_hls_playlist`, fetchers, parsing rules |
| [Downloading](python/downloading.md) | `download`, `Downloader`, output files, results, what is and is not supported |
| [Leftover folders](python/workspaces.md) | `find_workspaces`, `remove_workspaces`, `LeftoverWorkspace` |
| [Selecting tracks](python/selecting.md) | `select_stream`, `StreamSelection`, how quality, limits and languages are decided |
| [Settings](python/settings.md) | `DownloadConfig`, `NetworkConfig`, `ProxyConfig`, `OutputConfig`, `StorageConfig`, `SelectionConfig`, constants, secrets |
| [Models](python/models.md) | Every playlist, segment and download model, with fields, properties and methods |
| [Enums](python/enums.md) | Every enum and its members |
| [Events and cancellation](python/events.md) | `EventBus`, `DownloadEvent`, the state machine, `CancellationToken` (cancel, pause, resume) |
| [Errors](python/errors.md) | The `RayoHXError` hierarchy, attributes, handling patterns |
| [Logging](python/logging.md) | `configure_logging`, what is redacted, using your own handlers |

## Installation

RayoHX needs Python 3.11 or newer. Add it to a project with [uv](https://docs.astral.sh/uv/):

```bash
uv add RayoHX
```

or with pip:

```bash
pip install RayoHX
```

The package name is `RayoHX`, the import name is `rayohx`. Requests are made with `httpx`, and the
library does not need FFmpeg to inspect streams.

```python
import rayohx

print(rayohx.__version__)  # 0.1.0
```

## What is public

Names without a leading underscore are the public API. Anything starting with an underscore
(`rayohx._http`, `rayohx._crypto`, `rayohx._ratelimit`, `rayohx._redaction`, `rayohx._logs`, and
everything inside `rayohx._download`) is internal and can change in any release.

The top-level package loads its names the first time you use them, so `import rayohx` stays fast
and a front end loads only the parts it needs.

### Package map

```text
rayohx
├── (top level)       download, Downloader, inspect, inspect_playlist, parse_playlist,
│                     is_hls_playlist, select_stream, configure_logging, CancellationToken,
│                     __version__, the models and the enums
├── config            DownloadConfig, NetworkConfig, ProxyConfig, OutputConfig, StorageConfig,
│                     SelectionConfig, validate_url
├── models            every model, grouped in three packages
│   ├── playlist      MasterPlaylist, MediaPlaylist, Playlist, Variant, Resolution
│   │   └── tracks    AudioTrack, SubtitleTrack, VideoTrack
│   ├── segment       Segment, SegmentData, SegmentRange, EncryptionInfo, InitMap
│   └── download      DownloadRequest, DownloadProgress, DownloadResult, StorageMetrics, OutputInfo
├── downloader        download, Downloader: the whole job, and the controller behind it
├── playlist          the parser: parse_playlist, is_hls_playlist, inspect_playlist, PlaylistFetcher
├── stream            select_stream, StreamSelection
├── events            EventBus, DownloadEvent, DownloadStateMachine, TRANSITIONS
├── enums             DownloadState, EventType, StorageStrategy, and the other enums
├── errors            the RayoHXError hierarchy
├── cancellation      CancellationToken
├── logs              configure_logging
├── _download         internal: the engine that downloads segments (pipeline, storage, sinks, ...)
└── _http, _crypto, _ratelimit, _redaction, _logs     internal
```

You can import any model from `rayohx.models` without knowing which package holds it. The
sub-packages exist for people reading the source:

```python
from rayohx.models import Segment, Variant, DownloadResult  # recommended
from rayohx.models.segment import Segment  # also works
```

Errors and settings classes are imported from their own modules, not from the top-level package:

```python
from rayohx.config import NetworkConfig
from rayohx.errors import PlaylistNotFoundError
```

## Functions at a glance

| Function | Purpose | Page |
|---|---|---|
| `rayohx.download(url, output, **options)` | Download a stream to a file or a folder of segments | [Downloading](python/downloading.md#download) |
| `rayohx.download_many(urls, directory, **options)` | Download several streams, one after another, into a folder | [Downloading](python/downloading.md#download_many) |
| `rayohx.find_workspaces(folders=None, older_than_days=0)` | List working folders left by interrupted downloads | [Leftover folders](python/workspaces.md#find_workspaces) |
| `rayohx.remove_workspaces(workspaces)` | Delete those folders, skipping any in use | [Leftover folders](python/workspaces.md#remove_workspaces) |
| `rayohx.Downloader(url, ...)` | One download with events, state, pause/resume and cancellation | [Downloading](python/downloading.md#downloader) |
| `rayohx.inspect(url, network=None)` | Fetch and parse the playlist at a URL | [Inspecting](python/inspecting.md#inspect) |
| `rayohx.inspect_playlist(url, fetcher)` | The same, with a fetcher you supply | [Inspecting](python/inspecting.md#inspect_playlist) |
| `rayohx.inspect_text(text, base_url)` | Parse playlist text you already have | [Inspecting](python/inspecting.md#inspect_text) |
| `rayohx.parse_playlist(text, uri)` | Parse playlist text you already have | [Inspecting](python/inspecting.md#parse_playlist) |
| `rayohx.is_hls_playlist(text)` | `True` if the text starts with `#EXTM3U` | [Inspecting](python/inspecting.md#is_hls_playlist) |
| `rayohx.select_stream(master, config)` | Choose the video, audio and subtitle tracks | [Selecting](python/selecting.md) |
| `rayohx.configure_logging(level, *, console, log_file)` | Turn on logging for the `rayohx` logger | [Logging](python/logging.md) |
| `rayohx.config.validate_url(url, *, name)` | Check and clean an http(s) address | [Settings](python/settings.md#validate_url) |

URLs must be absolute `http` or `https` addresses. Anything else raises `ConfigurationError`.

## Conventions

- **Immutable and validated.** Models and settings are frozen dataclasses. A settings object checks
  itself when it is created and raises `ConfigurationError`; a model rejects impossible values with
  `ValueError` (for example a negative segment index). Collections are stored as tuples or
  read-only mappings.
- **Keyword-only fields.** Settings and models take keyword arguments, so adding a field never
  breaks existing code.
- **Secrets stay out.** Headers, cookies and proxy passwords are left out of `repr`, and `as_dict()`
  hides them, so a settings object is safe to log or store. Addresses in messages, events and logs
  have their credentials and query tokens removed.
- **Events, not prints.** The engine reports through `DownloadEvent` objects delivered by an
  `EventBus`. A listener that raises is logged and never stops the download.
- **Explicit states.** `DownloadStateMachine` allows only the moves in `TRANSITIONS`.
  A cancelled download ends as `CANCELLED`, not as a failure.
- **Errors say what to do.** Every `RayoHXError` has a redacted `message` and an optional `hint`.
- **Silent until asked.** Loggers live under `rayohx` and the library adds no handlers. Logs go to
  stderr, never stdout.
- **Thread safety.** Settings, models and results are immutable and safe to share. `EventBus`,
  `DownloadStateMachine` and `CancellationToken` are safe to use from several threads.

## Examples

Pick the best stream under a data budget, preferring English audio with German as a fallback:

```python
import rayohx
from rayohx.config import SelectionConfig

master = rayohx.inspect("https://cdn.example.com/vod/master.m3u8")
choice = rayohx.select_stream(
    master,
    SelectionConfig(max_bitrate=3_000_000, audio_languages=("en", "de")),
)
print(choice.variant.uri, choice.variant.bandwidth)
for note in choice.notes:
    print("note:", note)
```

Get the length of a video-on-demand stream:

```python
from rayohx.models import MasterPlaylist

playlist = rayohx.inspect("https://cdn.example.com/vod/360p/index.m3u8")
if not isinstance(playlist, MasterPlaylist) and playlist.is_vod:
    minutes, seconds = divmod(int(playlist.total_duration), 60)
    print(f"{playlist.segment_count} segments, {minutes}:{seconds:02d}")
```

Download a stream with progress, and stop it on demand:

```python
from rayohx import CancellationToken, download
from rayohx.enums import EventType

token = CancellationToken()


def show(event):
    if event.type is EventType.DOWNLOAD_PROGRESS and event.progress:
        print(f"{event.progress.fraction:.0%}")


result = download(
    "https://cdn.example.com/vod/master.m3u8", "video.ts", on_event=show, cancel=token
)
print("cancelled" if result.cancelled else result.output.path)
```

Test code that uses RayoHX without a network, by supplying a fetcher:

```python
class FakeFetcher:
    def fetch_text(self, url: str) -> tuple[str, str]:
        return MASTER_TEXT, url


def test_lists_variants() -> None:
    playlist = rayohx.inspect_playlist("https://cdn.example.com/master.m3u8", FakeFetcher())
    assert len(playlist.variants) == 3
```

More examples are on each page.

## Not yet available

These are planned and are not part of the library yet:

- **Merging separate tracks.** A stream that keeps its audio in a separate track needs a merge
  step. Use `video_only=True` to download the video alone, or `format="segments"` to save the
  pieces.
- **Saving subtitles.**
- **Remuxing.** MPEG-TS cannot be saved as MP4 yet; the file name has to match what is inside.
- **Live streams** and **protected (DRM) streams** are refused with an explanation.

See the [engine design](../engine.md) for the full picture.
