# Downloading

`download()` takes a web address to a finished file in one call. `Downloader` is the controller
behind it, for when you want to follow the download, cancel it, or read its state while it runs.

[Back to the Python guide](../python.md)

| Name | Module | Purpose |
|---|---|---|
| [`download(url, output, ...)`](#download) | `rayohx` | The whole job in one call |
| [`Downloader`](#downloader) | `rayohx` | One download, with events, state and cancellation |

Both live in `rayohx.downloader` and are also available from `rayohx`.

```python
from rayohx import download

result = download("https://example.com/master.m3u8", "video.ts", quality="1080p")
print(result.output.path, result.output.size_bytes)
```

## What a download does

1. **Inspecting.** Fetches the playlist. For a master playlist it chooses the stream with
   [`select_stream`](selecting.md) and fetches that stream's playlist.
2. **Preparing.** Works out the output file from the container (MPEG-TS or fragmented MP4), your
   file name and your format request; chooses the storage strategy; checks free disk space.
3. **Downloading.** Fetches segments in parallel, decrypts them (AES-128), checks each one against
   the container, and writes them in order.
4. **Finalizing.** Validates the finished file and puts it in place. Only then does the name you
   asked for exist: until then the data is in a `.part` file or folder, so a half-finished download
   is never mistaken for a finished one.

A download that is interrupted or cancelled continues where it stopped the next time you run it
(`resume`, on by default). With the default storage strategy your disk needs only the size of the
video, not twice that.

## What works today

- **MPEG-TS** streams are saved as `.ts` and **fragmented MP4** streams as `.mp4`. An MPEG-TS stream
  can also be saved as `.mp4`: it is re-wrapped without re-encoding.
- **Encrypted streams** (plain AES-128) work. Protected (DRM) streams, SAMPLE-AES and live streams
  are refused with an explanation.
- **A name that does not match what is inside** (for example `.mp4` for an MPEG-TS stream) is
  refused, never quietly mislabeled.
- **Streams with a separate audio track** are joined into one `.mp4`, using the audio you chose
  (see [`select_stream`](selecting.md)). Add `video_only=True` to download just the video instead.
- **Subtitles** you ask for are saved next to the video as `<name>.<language>.vtt` files that line
  up with it. Only WebVTT text is supported.
- **FFmpeg is optional.** The built-in remuxer copies H.264 and HEVC video with AAC, AC-3, E-AC-3
  and MP3 audio. For other codecs an FFmpeg already installed on your machine is used if there is
  one; otherwise the download fails with `UnsupportedCodecError`. FFmpeg is never required,
  shipped or asked to re-encode. See [`RemuxBackend`](enums.md#remuxbackend).
- **Re-wrapped downloads do not resume.** An interrupted download that joined audio or turned
  MPEG-TS into MP4 starts again; plain downloads keep resuming.
- **An existing file is never replaced** unless you add `overwrite=True`.

## download

```python
rayohx.download(
    url: str,
    output: Path | str | None = None,
    *,
    config: DownloadConfig | None = None,
    quality: str | None = None,
    max_resolution: str | None = None,
    max_bitrate: int | None = None,
    audio: str | Sequence[str] | None = None,
    subtitles: str | Sequence[str] | None = None,
    video_only: bool | None = None,
    format: OutputFormat | str | None = None,
    overwrite: bool | None = None,
    concurrency: int | None = None,
    resume: bool | None = None,
    on_event: Callable[[DownloadEvent], None] | None = None,
    cancel: CancellationToken | None = None,
) -> DownloadResult
```

Downloads the stream at `url` to `output`. Returns a [`DownloadResult`](models.md#downloadresult).
A completed download and a cancelled one both return a result; a failure raises.

| Parameter | Meaning |
|---|---|
| `url` | An absolute `http` or `https` address of a master or media playlist |
| `output` | A file name, or `None` to name the file after the address in the current folder. With no extension the right one is added (`video` becomes `video.ts`). With `format="segments"` it is a folder |
| `config` | A [`DownloadConfig`](settings.md#downloadconfig) for everything the keywords do not cover: headers, cookies, a proxy, timeouts, the storage strategy |
| `quality` | `best`, `worst`, `auto`, or a height such as `720p` (see [Selecting tracks](selecting.md)) |
| `max_resolution`, `max_bitrate` | Limits applied before the quality choice |
| `codec`, `video_range`, `max_frame_rate` | Prefer a codec or dynamic range, and cap the frame rate |
| `audio`, `subtitles` | A language code or a list of them |
| `video_only` | Download only the video stream, leaving out separate audio and subtitle tracks |
| `format` | `auto`, `ts`, `mp4` or `segments` (an [`OutputFormat`](enums.md#outputformat) or its name) |
| `overwrite` | Replace an existing file |
| `concurrency` | Segments fetched at the same time, 1 to 64 |
| `resume` | Continue an interrupted download |
| `on_event` | A listener for [events](events.md), subscribed before the download starts |
| `cancel` | A [`CancellationToken`](events.md#cancellationtoken) that stops the download |

The keyword options override `config`; an option left as `None` keeps the value from `config`.

```python
from rayohx import download
from rayohx.config import DownloadConfig, NetworkConfig

config = DownloadConfig(network=NetworkConfig(headers={"Referer": "https://site.example/"}))
result = download(
    "https://cdn.example.com/vod/master.m3u8",
    "show.ts",
    config=config,
    max_resolution="720p",
    concurrency=8,
)
```

**What it returns and raises:**

| Outcome | What you get |
|---|---|
| Completed | A `DownloadResult` with `state == COMPLETED`, `success` true and `output` set |
| Cancelled | A `DownloadResult` with `state == CANCELLED`, `cancelled` true, no `output` and no `error` |
| Failed | The original exception is raised: a `RayoHXError` with a message and a hint |
| Bad option | `ConfigurationError` for an invalid address, `concurrency` or other setting; `ValueError` for an unknown `format` name |

```python
from rayohx.errors import RayoHXError

try:
    result = download(url, "video.ts")
except RayoHXError as exc:
    print(exc.describe())
else:
    print("cancelled" if result.cancelled else f"saved {result.output.path}")
```

## download_many

```python
rayohx.download_many(
    urls: Sequence[str],
    directory: Path | str | None = None,
    *,
    config: DownloadConfig | None = None,
    stop_on_error: bool = False,
    on_event: Callable[[DownloadEvent], None] | None = None,
    cancel: CancellationToken | None = None,
) -> list[BatchItem]
```

Downloads each address in turn into `directory` (or `config.output.directory`, or the current
folder). Files are named after their addresses; two addresses that would get the same name get
`-2`, `-3` and so on, and `rayohx.batch_outputs(urls, directory)` shows the names beforehand.

- `config` applies to every download. `config.output.path` is ignored.
- All addresses are checked first, so a bad one raises `ConfigurationError` before anything is
  downloaded. An empty list does too.
- A failed download is not raised. Look at each `BatchItem`: `url`, `output`, `result`,
  `exception`, and the `success` and `skipped` properties.
- One failure does not stop the others unless `stop_on_error=True`. Cancelling through `cancel`
  always stops the batch, and what was not started is reported as `skipped`.

```python
items = rayohx.download_many(urls, "videos", quality="720p")
for item in items:
    print(item.url, "ok" if item.success else "skipped" if item.skipped else item.exception)
```

## Downloader

```python
rayohx.Downloader(
    url: str,
    *,
    output: Path | str | None = None,
    config: DownloadConfig | None = None,
    events: EventBus | None = None,
    cancel: CancellationToken | None = None,
    download_id: str | None = None,
    transport: httpx.BaseTransport | None = None,
    clock: Callable[[], float] = time.monotonic,
)
```

Downloads one stream. Create it, optionally subscribe to `events`, then call `run`. A `Downloader`
runs once.

| Parameter | Meaning |
|---|---|
| `url` | The playlist address (validated when you create the object) |
| `output` | The output file or folder; defaults to `config.output.path` |
| `config` | The settings; defaults to `DownloadConfig()` |
| `events` | An existing `EventBus` to emit on; a new one is created if you give none |
| `cancel` | A token to stop the download; a new one is created if you give none |
| `download_id` | The identifier for events and log lines; 12 random hex characters if none |
| `transport` | A replacement `httpx` transport, for tests |
| `clock` | A replacement clock, for tests |

| Member | Returns |
|---|---|
| `run()` | A `DownloadResult` |
| `cancel()` | `None`. Asks the download to stop; safe from any thread and safe to call more than once |
| `pause()` | `None`. Stops new segments from starting until `resume()`; segments already running finish first. Safe from any thread, also before `run()` |
| `resume()` | `None`. Goes on after `pause()`; does nothing if the download is not paused |
| `is_paused` (property) | Whether the download is waiting for `resume()` |
| `download_id` (property) | The identifier events and log lines carry |
| `state` (property) | Where the download is now (a `DownloadState`) |
| `events` (property) | The `EventBus`; subscribe here to follow the download |
| `exception` (attribute) | The error that ended the download, when it failed; otherwise `None` |

**`run()` never raises for a failed download.** It returns a result in the `FAILED` state with the
message in `error`, and keeps the original exception in `exception`. (`download()` raises that
exception for you.) Calling `run()` a second time raises `DownloadError`.

| How it ended | `result.state` | `result.error` | `result.output` | `downloader.exception` |
|---|---|---|---|---|
| Completed | `COMPLETED` | `None` | the file | `None` |
| Cancelled | `CANCELLED` | `None` | `None` | `None` |
| Failed | `FAILED` | message and hint | `None` | the error |

```python
from rayohx import Downloader

downloader = Downloader("https://cdn.example.com/vod/master.m3u8", output="video.ts")
downloader.events.subscribe(lambda event: print(event.type.name))

result = downloader.run()
if result.success:
    print("saved", result.output.path)
elif result.cancelled:
    print("cancelled")
else:
    print("failed:", result.error)  # message and hint
    raise downloader.exception  # the original error, if you want it
```

An error found while creating the object, such as an invalid address, is raised straight away and
not returned in a result:

```python
Downloader("ftp://x")  # ConfigurationError: url must be an absolute http or https address ...
```

## Output files

| You pass | `format` | You get |
|---|---|---|
| `"video.ts"` | any / auto | `video.ts` for an MPEG-TS stream; an error for an fMP4 stream or a stream with separate audio |
| `"video.mp4"` | any / auto | `video.mp4` for an fMP4 stream; for an MPEG-TS stream the segments are re-wrapped into it |
| `"video"` | auto | The right extension added: `video.ts` or `video.mp4` (always `.mp4` when audio is joined) |
| `None` | auto | A file named after the address in the current folder (or `OutputConfig(directory=...)`), such as `my-show.ts` |
| `"parts"` | `segments` | A folder `parts/` with `segment-00001.ts`, `segment-00002.ts`, ... and `init-00001.mp4` for fMP4 |

- An explicit `format` must agree with the file name; `format="mp4"` for a `.ts` name is an error.
- Files ending in an extension RayoHX does not know are refused.
- Names made from an address are safe: letters, digits, dots, dashes and underscores only, never a
  Windows device name, never a path separator.
- A playlist that contains only subtitles, or whose format cannot be recognised, is refused.
- The result's `output.size_bytes` for a folder is the total size of the segment files.
- A folder of segments cannot resume: running it again starts over.
- Separate audio and subtitles cannot be saved as `format="segments"`; use `video_only=True` or a
  different format.
- Subtitle files are named after the output: `video.mp4` with English subtitles gives
  `video.en.vtt`. A name that is already taken gets a number (`video.en2.vtt`), and an existing
  subtitle file blocks the download unless you add `overwrite=True`.

While a download runs, the data is in `<name>.part` (a file, or a folder for `segments`). It is
renamed only when the download is complete and validated.

## Events during a download

`Downloader` emits these events, in this order, on its `EventBus`:

| Step | Event | State | Details |
|---|---|---|---|
| Start | `DOWNLOAD_STARTED` | `QUEUED` | `message` is the address with secrets removed |
| Fetching the playlist | `PLAYLIST_LOADED` | `INSPECTING` | `data["kind"]` is `"master"` or `"media"` |
| Choosing a stream | `STREAM_SELECTED` | `INSPECTING` | `data` has `bandwidth`, `resolution`, `codecs`, `audio`, `subtitles`, `notes` |
| Fetching the stream | `PLAYLIST_LOADED` | `INSPECTING` | `data["kind"]` is `"media"` |
| Each segment | `SEGMENT_STARTED`, `SEGMENT_COMPLETED` | `DOWNLOADING` | `segment_index`; completed also has `data["bytes"]` |
| Periodically | `DOWNLOAD_PROGRESS` | `DOWNLOADING` | `progress` |
| When paused or resumed | `DOWNLOAD_PAUSED`, `DOWNLOAD_RESUMED` | `PAUSED`, `DOWNLOADING` | `progress` |
| After the last segment | `FINALIZATION_STARTED` | `FINALIZING` | `progress` |
| After validation | `FINALIZATION_COMPLETED` | `FINALIZING` | `message` is the output path |
| End | `DOWNLOAD_COMPLETED` | `COMPLETED` | `message` is the output path, `progress` |

A failed segment emits `SEGMENT_FAILED` (with the reason in `message`). A failed download ends with
`DOWNLOAD_FAILED` and a cancelled one with `DOWNLOAD_CANCELLED`; both carry `message`, `progress`
and `data["hint"]`. The `PREPARING` state has no event of its own. See
[Events and cancellation](events.md) for the event model.

## Examples

A progress line that updates in place:

```python
from rayohx import download
from rayohx.enums import EventType


def show(event):
    if event.type is EventType.DOWNLOAD_PROGRESS and event.progress:
        p = event.progress
        print(
            f"\r{p.fraction:6.1%}  {p.speed / 1e6:5.1f} MB/s  {p.completed_segments}/{p.total_segments}",
            end="",
        )


download("https://cdn.example.com/vod/master.m3u8", "video.ts", on_event=show)
```

Stop a download from another thread, for example on Ctrl+C or a button:

```python
import threading
from rayohx import CancellationToken, Downloader

token = CancellationToken()
downloader = Downloader("https://cdn.example.com/vod/master.m3u8", output="video.ts", cancel=token)

worker = threading.Thread(target=downloader.run)
worker.start()
...
downloader.cancel()  # or token.cancel()
worker.join()
```

Pause a download and go on later. A pause takes a moment to show, because segments already being
fetched finish first. Cancelling a paused download stops it. A download that is already finalizing
carries on to the end:

```python
downloader.pause()
print(downloader.is_paused)  # True once the download is waiting
...
downloader.resume()
```

Download the video of a stream that keeps its audio in a separate track:

```python
download("https://cdn.example.com/vod/master.m3u8", "video.ts", video_only=True)
```

Join a separate audio track into the video and save English subtitles beside it:

```python
download(
    "https://cdn.example.com/vod/master.m3u8",
    "video.mp4",
    audio="en",
    subtitles="en",
)
# video.mp4 and video.en.vtt
```

Re-wrap an MPEG-TS stream into MP4 using only the built-in remuxer:

```python
from rayohx import RemuxBackend
from rayohx.config import DownloadConfig, OutputConfig

config = DownloadConfig(output=OutputConfig(remux_backend=RemuxBackend.NATIVE))
download("https://cdn.example.com/vod/media.m3u8", "video.mp4", config=config)
```

Save the pieces and join them yourself:

```python
download("https://cdn.example.com/vod/master.m3u8", "parts", format="segments")
# parts/segment-00001.ts, parts/segment-00002.ts, ...
```

Resume after an interruption: just run the same call again. The `.part` data and the saved state
are picked up where they ended:

```python
download(url, "video.ts")  # interrupted by a crash or Ctrl+C
download(url, "video.ts")  # continues
download(url, "video.ts", resume=False)  # starts over
```

Replace a file you already have:

```python
download(url, "video.ts", overwrite=True)
```

Name the file after the address, in the current folder:

```python
result = download("https://cdn.example.com/shows/my-show/index.m3u8")
print(result.output.path)  # .../my-show.ts
```

Show why a download failed without raising:

```python
downloader = Downloader(url, output="video.ts")
result = downloader.run()
if result.state.name == "FAILED":
    print(result.error)
    # Joining a separate audio track into the video needs an MP4 file. Save it as .mp4.
```
