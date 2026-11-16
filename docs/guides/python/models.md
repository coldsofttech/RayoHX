# Models

Everything the library returns is a frozen dataclass with keyword-only fields. Nothing is changed in
place, so models are safe to share between threads. A model rejects impossible values with
`ValueError` (for example a negative segment index). Models carry data and simple derived values
only; parsing, selecting and downloading live elsewhere.

[Back to the Python guide](../python.md)

Import any model from `rayohx.models`; most are also available from `rayohx` itself:

```python
from rayohx.models import MasterPlaylist, MediaPlaylist, Segment, Variant
import rayohx

rayohx.Segment is Segment  # True
```

In the source the models are grouped in three packages, each also importable directly:

| Package | Models |
|---|---|
| [`rayohx.models.playlist`](#playlists) | `MasterPlaylist`, `MediaPlaylist`, `Playlist`, `Variant`, `Resolution`, and in `tracks`: `AudioTrack`, `SubtitleTrack`, `VideoTrack` |
| [`rayohx.models.segment`](#segments) | `Segment`, `SegmentData`, `SegmentRange`, `EncryptionInfo`, `InitMap` |
| [`rayohx.models.download`](#downloads) | `DownloadRequest`, `DownloadProgress`, `DownloadResult`, `StorageMetrics`, `OutputInfo` |

## Playlists

### Playlist

`Playlist = MasterPlaylist | MediaPlaylist`. The return type of `inspect` and `parse_playlist`.

```python
from rayohx.models import MasterPlaylist, MediaPlaylist, Playlist


def describe(playlist: Playlist) -> str:
    if isinstance(playlist, MasterPlaylist):
        return f"{len(playlist.variants)} streams"
    return f"{playlist.segment_count} segments"
```

### MasterPlaylist

A playlist of variants and the tracks that go with them.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `uri` | `str` | required | The address the playlist came from |
| `variants` | `tuple[Variant, ...]` | required | The video streams on offer |
| `video_tracks` | `tuple[VideoTrack, ...]` | `()` | Alternative video renditions |
| `audio_tracks` | `tuple[AudioTrack, ...]` | `()` | Audio renditions |
| `subtitle_tracks` | `tuple[SubtitleTrack, ...]` | `()` | Subtitle renditions |
| `version` | `int \| None` | `None` | The `EXT-X-VERSION` |

| Method | Returns |
|---|---|
| `audio_group(group_id)` | The audio tracks of one group (`tuple[AudioTrack, ...]`) |
| `subtitle_group(group_id)` | The subtitle tracks of one group (`tuple[SubtitleTrack, ...]`) |

```python
variant = master.variants[0]
if variant.audio_group:
    for track in master.audio_group(variant.audio_group):
        print(track.language, track.name, track.default)
```

### MediaPlaylist

A playlist of segments.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `uri` | `str` | required | The address the playlist came from |
| `segments` | `tuple[Segment, ...]` | required | The segments in order |
| `target_duration` | `float` | required | `EXT-X-TARGETDURATION` in seconds |
| `media_sequence` | `int` | `0` | Sequence number of the first segment |
| `end_list` | `bool` | `False` | Whether `EXT-X-ENDLIST` was present |
| `version` | `int \| None` | `None` | The `EXT-X-VERSION` |
| `playlist_type` | `str \| None` | `None` | `VOD` or `EVENT` when stated |
| `container` | `ContainerFormat` | `ContainerFormat.UNKNOWN` | How the segments are packaged, as far as the playlist says |

| Property | Returns |
|---|---|
| `segment_count` | Number of segments |
| `total_duration` | Sum of the segment durations, in seconds |
| `is_vod` | Whether the playlist is complete and will not grow (`end_list` or type `VOD`) |

```python
media = rayohx.inspect("https://cdn.example.com/vod/360p/index.m3u8")
print(media.segment_count, media.total_duration, media.is_vod, media.container)
# 3 15.5 True ContainerFormat.MPEG_TS
```

### Variant

One `EXT-X-STREAM-INF` entry: a rendition of the video.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `uri` | `str` | required | The address of the media playlist |
| `bandwidth` | `int` | required | Peak bits per second |
| `average_bandwidth` | `int \| None` | `None` | Average bits per second |
| `resolution` | `Resolution \| None` | `None` | Picture size when stated |
| `codecs` | `tuple[str, ...]` | `()` | Codec strings such as `avc1.4d401e` |
| `frame_rate` | `float \| None` | `None` | Frames per second |
| `video_range` | `str \| None` | `None` | `SDR`, `PQ` or `HLG` |
| `video_group` | `str \| None` | `None` | Video rendition group |
| `audio_group` | `str \| None` | `None` | Audio rendition group |
| `subtitle_group` | `str \| None` | `None` | Subtitle rendition group |
| `name` | `str \| None` | `None` | Human-readable name when given |

Property: `height`, the picture height in pixels when known (otherwise `None`).

### Resolution

Width and height in pixels. Both must be positive.

| Field | Type | Meaning |
|---|---|---|
| `width` | `int` | Pixels across |
| `height` | `int` | Pixels down |

Property: `pixels`, the total pixel count.

### Tracks

The renditions a master playlist offers next to its video streams. In
`rayohx.models.playlist.tracks`, also importable from `rayohx.models`.

**`AudioTrack`**

| Field | Type | Default | Meaning |
|---|---|---|---|
| `group_id` | `str` | required | The group it belongs to |
| `name` | `str` | required | Display name |
| `language` | `str \| None` | `None` | Language code |
| `uri` | `str \| None` | `None` | Its own playlist; `None` when the audio is inside the video segments |
| `default` | `bool` | `False` | Chosen by default |
| `autoselect` | `bool` | `False` | May be chosen automatically |
| `forced` | `bool` | `False` | Forced track |
| `channels` | `str \| None` | `None` | Channel layout, for example `2` |
| `characteristics` | `tuple[str, ...]` | `()` | `CHARACTERISTICS` values |

**`SubtitleTrack`**: the same fields as `AudioTrack` except `channels`.

**`VideoTrack`**: an alternative video rendition.

| Field | Type | Default |
|---|---|---|
| `group_id` | `str` | required |
| `name` | `str` | required |
| `uri` | `str \| None` | `None` |
| `default` | `bool` | `False` |
| `autoselect` | `bool` | `False` |

## Segments

### Segment

One media segment, with everything needed to fetch and place it. `index` must not be negative and
`duration` must not be negative.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `index` | `int` | required | Position in the playlist, from 0 |
| `uri` | `str` | required | Absolute address |
| `duration` | `float` | required | Seconds |
| `sequence_number` | `int` | required | Media sequence number (used for the implicit IV) |
| `byte_range` | `SegmentRange \| None` | `None` | The part of the resource this segment is |
| `init_map` | `InitMap \| None` | `None` | Initialization section for fMP4 |
| `encryption` | `EncryptionInfo \| None` | `None` | How it is encrypted |
| `discontinuity` | `bool` | `False` | A discontinuity precedes it |
| `program_date_time` | `datetime \| None` | `None` | Wall-clock time of its first sample |
| `title` | `str` | `""` | The `EXTINF` title |

### SegmentRange

A byte range inside a resource. `length` must be positive.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `length` | `int` | required | Bytes |
| `offset` | `int \| None` | `None` | First byte; `None` when it follows the previous range |

Method: `http_header()` returns the `Range` header value, such as `bytes=100-199`. It needs an
offset.

```python
from rayohx.models import SegmentRange

SegmentRange(length=100, offset=100).http_header()  # 'bytes=100-199'
```

### InitMap

An `EXT-X-MAP` initialization section.

| Field | Type | Default |
|---|---|---|
| `uri` | `str` | required |
| `byte_range` | `SegmentRange \| None` | `None` |

### EncryptionInfo

An `EXT-X-KEY` entry. The key itself is fetched later, by the engine.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `method` | `EncryptionMethod` | required | `NONE`, `AES_128` or `SAMPLE_AES` |
| `uri` | `str \| None` | `None` | Where the key is |
| `iv` | `bytes \| None` | `None` | The IV; `None` means derive it from the sequence number |
| `key_format` | `str` | `"identity"` | `KEYFORMAT` |
| `key_format_versions` | `str \| None` | `None` | `KEYFORMATVERSIONS` |

| Member | Returns |
|---|---|
| `is_supported` (property) | Whether the engine can decrypt this entry: plain AES-128, no DRM key format |
| `EncryptionInfo.parse_iv(text)` (static) | The 16 bytes of an `IV` attribute such as `0x00112233445566778899aabbccddeeff` |

```python
stream_is_downloadable = all(
    segment.encryption is None or segment.encryption.is_supported for segment in media.segments
)
```

### SegmentData

A downloaded segment, decrypted. `init` is the initialization section to write first.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `index` | `int` | required | The segment's index |
| `media` | `bytes` | required | The decrypted media bytes |
| `init` | `bytes` | `b""` | The initialization section, when this segment needs it written first |

Property: `size`, the bytes this segment adds to the output (`len(init) + len(media)`).

## Downloads

Models that describe a download. The engine fills them in; front ends read them.

### DownloadRequest

A web address to download and the settings to download it with.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `url` | `str` | required | The playlist address (validated as http or https) |
| `config` | `DownloadConfig` | `DownloadConfig()` | The settings |

Property: `redacted_url`, the address with credentials and query tokens hidden, for logs and
messages. `repr` shows the redacted address.

### DownloadProgress

A snapshot of a download, ready to show in any front end.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `state` | `DownloadState` | `QUEUED` | Where the download is |
| `downloaded_bytes` | `int` | `0` | Bytes received, including retried attempts |
| `written_bytes` | `int` | `0` | Bytes written to the output |
| `total_bytes` | `int \| None` | `None` | Expected total, when known |
| `completed_segments` | `int` | `0` | Segments finished |
| `total_segments` | `int` | `0` | Segments in the stream |
| `speed` | `float` | `0.0` | Current bytes per second |
| `average_speed` | `float` | `0.0` | Average bytes per second |
| `eta_seconds` | `float \| None` | `None` | Estimated seconds left |
| `active_workers` | `int` | `0` | Segments being fetched now |
| `storage` | `StorageMetrics` | `StorageMetrics()` | What is held in memory and on disk |

Property: `fraction`, the share done between 0 and 1. It uses bytes when the total is known, else
segments.

```python
def show(progress: DownloadProgress) -> str:
    return f"{progress.fraction:.0%} at {progress.speed / 1e6:.1f} MB/s, {progress.eta_seconds or 0:.0f}s left"
```

### DownloadResult

How a download ended. A cancelled download has its own state, not a failure.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `download_id` | `str` | required | The identifier events and log lines carry |
| `url` | `str` | required | The playlist address (redacted) |
| `state` | `DownloadState` | required | The final state |
| `elapsed_seconds` | `float` | required | How long it took |
| `progress` | `DownloadProgress` | required | The last snapshot |
| `output` | `OutputInfo \| None` | `None` | The produced file, when there is one |
| `error` | `str \| None` | `None` | A short description when it failed |

Properties: `success` (the download completed) and `cancelled` (it was cancelled).

```python
if result.success:
    print("Saved", result.output.path)
elif result.cancelled:
    print("Cancelled")
else:
    print("Failed:", result.error)
```

### StorageMetrics

A snapshot of how much data the download has moved and kept, in bytes.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `output_bytes` | `int` | `0` | Written to the output (the same figure as `written_bytes`) |
| `temporary_bytes` | `int` | `0` | Held as temporary files now |
| `working_bytes` | `int` | `0` | Held in memory and as temporary files now |
| `peak_temporary_bytes` | `int` | `0` | The most temporary data held at once |
| `downloaded_bytes` | `int` | `0` | Received from the network so far, including attempts that were retried |
| `written_bytes` | `int` | `0` | Written so far |

### OutputInfo

The file a download produced.

| Field | Type | Meaning |
|---|---|---|
| `path` | `Path` | Where it is |
| `container` | `ContainerFormat` | How it is packaged |
| `size_bytes` | `int` | Its size |

## Examples

Count the segments of a media playlist that are encrypted:

```python
encrypted = sum(1 for s in media.segments if s.encryption is not None)
print(f"{encrypted} of {media.segment_count} segments are encrypted")
```

Find the init section of an fMP4 stream:

```python
first = media.segments[0]
if first.init_map is not None:
    print("init section:", first.init_map.uri, first.init_map.byte_range)
```

Group variants by height:

```python
from collections import defaultdict

by_height = defaultdict(list)
for variant in master.variants:
    by_height[variant.height].append(variant)
```

Use a model as a dictionary key or in a set. Models are frozen, so they are hashable when their
fields are:

```python
seen = {segment.uri for segment in media.segments}
```
