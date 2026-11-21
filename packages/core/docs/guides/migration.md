# Moving from pym3u8downloader

RayoHX replaces `pym3u8downloader`. It is a new package with a different, much larger feature set, so there is no compatibility layer: update your calls as shown below. This page covers the library, `pym3u8downloader` 0.1.8 and earlier; every section shows the old code (before) and the new code (after).

```bash
pip uninstall pym3u8downloader
pip install rayohx
```

## What changed

- **Output is real.** `pym3u8downloader` always wrote the segments joined together, whatever the file was called. RayoHX saves MPEG-TS as `.ts` and fragmented MP4 as `.mp4`, can turn MPEG-TS into a genuine `.mp4` (`format="mp4"`) without FFmpeg, and joins separate audio tracks. A name that does not match the content is refused rather than mislabelled.
- **A function instead of a class.** You call `download(url, output)` instead of building an `M3U8Downloader` and calling a method. A `Downloader` class exists for when you need control (events, cancel), but nothing has to be constructed first.
- **One entry point** for playlists and master playlists. There is no `download_master_playlist`; the same call detects the kind and chooses a stream.
- **Settings are typed objects** (`DownloadConfig` and its parts) instead of constructor arguments and property setters.
- **Nothing is printed.** The old package drew progress bars on its own. RayoHX never prints; you ask for progress events (see [Progress](#progress)).
- **Errors are raised, not stored.** A failed download raises an exception with a message and a hint, and there is no `is_download_complete` flag to poll.
- **No internet pre-check, no temporary folder in the system temp.** Errors come from the actual request. Working files live beside the output (or in `workspace_dir`) and are cleaned up, and an interrupted download resumes.
- **Python 3.11 or newer**, and `httpx` instead of `requests`.

## Mapping at a glance

| pym3u8downloader | RayoHX |
| --- | --- |
| `M3U8Downloader(input_file_path=url, output_file_path="out").download_playlist()` | `download(url, "out.ts")` |
| `download_master_playlist(name=..., bandwidth=..., resolution="1280x720")` | `download(url, "out.mp4", config=DownloadConfig(selection=SelectionConfig(variant_name=..., bandwidth=..., resolution="1280x720")))` |
| `download_master_playlist()` returning the variants as JSON (`M3U8DownloaderWarning.json_data`) | `playlist_to_dict(inspect(url))` |
| `download_playlist(merge=False)` | `download(url, "folder", format="segments")` |
| `max_threads=10` | `concurrency=10` (1 to 64, default 4) |
| `verify_ssl=False` | `NetworkConfig(verify_tls=False)` (a warning is logged), or `verify_tls=Path("ca.pem")` for a private CA |
| `skip_space_check=True` | `StorageConfig(check_space=False)` |
| `debug=True, debug_file_path="debug.log"` | `configure_logging("DEBUG", log_file="debug.log")`; secrets are removed |
| `is_download_complete` | `result.success` |
| `M3U8DownloaderError` | `RayoHXError` and its subclasses (for example `SegmentDownloadError`, `OutputExistsError`) |
| `M3U8DownloaderWarning` | none: nothing is raised to pass data back |

## Downloading a playlist

**Before**

```python
from pym3u8downloader import M3U8Downloader

downloader = M3U8Downloader(
    input_file_path="https://example.com/video.m3u8",
    output_file_path="output_video",
)
downloader.download_playlist()
```

**After**

```python
import rayohx

result = rayohx.download("https://example.com/video.m3u8", "output_video.ts")
print(result.output.path, result.output.size_bytes)
```

The old call wrote the joined segments to `output_video` whatever they were. Give the new call a name with the right extension (`.ts` for MPEG-TS, `.mp4` for fragmented MP4), or leave the output out and the file is named after the address in the current folder. To get a real `.mp4` from MPEG-TS, ask for it:

```python
rayohx.download(url, "output_video.mp4", format="mp4")
```

An existing file is never replaced unless you pass `overwrite=True`; otherwise `OutputExistsError` is raised.

## Downloading a master playlist

The old package had a separate method for master playlists, and its arguments picked the variant. RayoHX uses the same `download()` and a `SelectionConfig`.

**Before**

```python
downloader = M3U8Downloader(
    input_file_path="https://example.com/master.m3u8",
    output_file_path="output_video",
)
downloader.download_master_playlist(name="720")
downloader.download_master_playlist(bandwidth="2500000", resolution="1280x720")
```

**After**

```python
from rayohx import download
from rayohx.config import DownloadConfig, SelectionConfig

selection = SelectionConfig(variant_name="720")
download(url, "output_video.mp4", config=DownloadConfig(selection=selection))

selection = SelectionConfig(bandwidth=2_500_000, resolution="1280x720")
download(url, "output_video.mp4", config=DownloadConfig(selection=selection))
```

- `bandwidth` is a number now, not text. It matches a variant's bandwidth or its average bandwidth.
- `variant_name` matches a variant's name exactly, ignoring case. `resolution` matches the picture size exactly, such as `"1280x720"`.
- If nothing matches, a `ConfigurationError` lists the streams that exist, so a wrong guess shows you the choices.

You do not have to match exactly any more. These pick a stream by number or by quality, and the keyword options of `download()` are enough for the common cases:

```python
download(url, "video.mp4", quality="720p")  # the best stream up to 720p
download(url, "video.mp4", quality="best")  # the default
download(url, "video.mp4", max_resolution="1080p", audio="en", subtitles="en")

download(
    url, "video.mp4", config=DownloadConfig(selection=SelectionConfig(variant=2))
)  # the 2nd in the list
```

## Listing the variants

The old package returned the variants only when you called `download_master_playlist()` with no arguments, in the `json_data` of an `M3U8DownloaderWarning`. RayoHX has an explicit call that downloads nothing.

**Before**

```python
from pym3u8downloader import M3U8Downloader, M3U8DownloaderWarning

downloader = M3U8Downloader(input_file_path=url, output_file_path="output_video")
try:
    downloader.download_master_playlist()
except M3U8DownloaderWarning as warning:
    variants = warning.json_data
```

**After**

```python
import rayohx

playlist = rayohx.inspect(url)
for index, variant in enumerate(playlist.variants, start=1):
    print(index, variant.name, variant.resolution, variant.bandwidth)

data = rayohx.playlist_to_dict(playlist)  # plain data, ready for json.dumps
variants = data["variants"]  # index, name, resolution, bandwidth, codecs, url ...
```

To see which stream a set of wishes would pick, without downloading:

```python
from rayohx.config import SelectionConfig

choice = rayohx.select_stream(playlist, SelectionConfig(quality="720p"))
print(choice.variant.uri, choice.notes)
```

## Keeping the segments separate

**Before**

```python
downloader.download_playlist(merge=False)
```

**After**

```python
rayohx.download(url, "segments_folder", format="segments")
```

The output is a folder. Each segment is saved as `segment-00001.ts`, `segment-00002.ts` and so on inside it.

## Threads, TLS and the space check

**Before**

```python
downloader = M3U8Downloader(
    input_file_path=url,
    output_file_path="output_video",
    max_threads=20,
    verify_ssl=False,
    skip_space_check=True,
)
downloader.download_playlist()
```

**After**

```python
from pathlib import Path

from rayohx import download
from rayohx.config import DownloadConfig, NetworkConfig, StorageConfig

config = DownloadConfig(
    concurrency=20,  # 1 to 64, default 4
    network=NetworkConfig(verify_tls=False),  # logs a warning every time
    storage=StorageConfig(check_space=False),
)
download(url, "output_video.ts", config=config)
```

Prefer fixing the certificate to turning verification off. For a private certificate authority, point `verify_tls` at its file:

```python
NetworkConfig(verify_tls=Path("company-ca.pem"))
```

Other settings the old package had no equivalent for are in the same objects: headers and cookies, a proxy, retries and back-off, a speed limit, the storage strategy and the working folder. See the [Python guide](python.md).

## Debug logging

**Before**

```python
downloader = M3U8Downloader(
    input_file_path=url,
    output_file_path="output_video",
    debug=True,
    debug_file_path="debug.log",
)
```

**After**

```python
import rayohx

rayohx.configure_logging("DEBUG", log_file="debug.log")
rayohx.download(url, "output_video.ts")
```

Call `configure_logging` once, before downloading. It writes to the screen (stderr) and to the file, and removes URLs' tokens, `Authorization`, cookies and proxy passwords from what it writes. Pass `console=False` to write to the file only. Nothing is written to `debug.log` unless you ask.

## Progress

The old package printed three progress bars (verify, download, build). RayoHX prints nothing; you receive events and show what you like.

**Before**

```text
Verify  : [##################################################] 100%
Download: [##################################################] 100%
Build   : [##################################################] 100%
```

**After**

```python
from rayohx import EventType, download


def show(event):
    if event.type is EventType.DOWNLOAD_PROGRESS and event.progress is not None:
        fraction = event.progress.fraction
        if fraction is not None:
            print(f"\r{fraction:6.1%}", end="")


download(url, "output_video.ts", on_event=show)
```

`event.progress` carries the bytes and segments done, the speed and an estimated time left. The events cover the other steps too (`PLAYLIST_LOADED`, `STREAM_SELECTED`, `FINALIZATION_STARTED` and so on).

## Success and errors

**Before**

```python
from pym3u8downloader import M3U8Downloader, M3U8DownloaderError

downloader = M3U8Downloader(input_file_path=url, output_file_path="output_video")
try:
    downloader.download_playlist()
except M3U8DownloaderError as error:
    print(error)
if downloader.is_download_complete:
    print("done")
```

**After**

```python
from rayohx import download
from rayohx.errors import OutputExistsError, RayoHXError

try:
    result = download(url, "output_video.ts")
except OutputExistsError:
    print("The file is already there; pass overwrite=True to replace it.")
except RayoHXError as error:
    print(error.message, error.hint)  # error.describe() joins them
else:
    if result.success:
        print("done", result.output.path)
    elif result.cancelled:
        print("stopped")
```

- Every error RayoHX raises on purpose derives from `RayoHXError` and has a `message` and an optional `hint` saying what to try. Catch the base class to catch them all, or a subclass for a specific case.
- A failed download raises. A cancelled one returns a result with `cancelled` set, so check it when you cancel.
- Settings mistakes (a bad address, an unknown stream) raise `ConfigurationError` before any request is made.

## Resuming and cancelling

The old package started from the beginning every time. RayoHX resumes an interrupted download by default (`resume=True`), picking up where it stopped as long as the address and output are the same. To stop a download from another thread:

```python
from rayohx import CancellationToken, download

token = CancellationToken()
# ... in another thread, when the user asks:  token.cancel()
result = download(url, "output_video.ts", cancel=token)
print(result.cancelled)
```

## Things the old project could not do

Encrypted (AES-128) streams, audio and subtitle tracks, fragmented MP4, retries with back-off, a speed limit, a proxy, headers and cookies, resume, cancellation, progress events, JSON output, and FFmpeg-free MP4 output.
