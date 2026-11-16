# Enums

Every choice the library offers is an enum in `rayohx.enums`, and all eight are also available from
`rayohx`. Each member has a stable string `value` that is safe to store, log or send over the API.

[Back to the Python guide](../python.md)

```python
from rayohx import DownloadState
from rayohx.enums import StorageStrategy

DownloadState.COMPLETED.value  # 'completed'
StorageStrategy("temporary")  # <StorageStrategy.TEMPORARY: 'temporary'>
```

| Enum | Used by |
|---|---|
| [`ContainerFormat`](#containerformat) | `MediaPlaylist.container`, `OutputInfo.container` |
| [`DownloadState`](#downloadstate) | `DownloadProgress.state`, `DownloadEvent.state`, `DownloadResult.state`, `DownloadStateMachine` |
| [`EncryptionMethod`](#encryptionmethod) | `EncryptionInfo.method` |
| [`EventType`](#eventtype) | `DownloadEvent.type` |
| [`OutputFormat`](#outputformat) | `OutputConfig.format` |
| [`RemuxBackend`](#remuxbackend) | `OutputConfig.remux_backend` |
| [`SegmentState`](#segmentstate) | The life cycle of one segment |
| [`StorageStrategy`](#storagestrategy) | `StorageConfig.strategy` |

## ContainerFormat

How the segments of a stream are packaged.

| Member | Value | Meaning |
|---|---|---|
| `MPEG_TS` | `"mpeg-ts"` | MPEG transport stream segments |
| `FMP4` | `"fmp4"` | Fragmented MP4: an init segment plus fragments |
| `WEBVTT` | `"webvtt"` | WebVTT subtitle segments |
| `UNKNOWN` | `"unknown"` | Not clear from the playlist; the first bytes of a segment settle it |

## DownloadState

Where a download is in its life cycle. Moves between states are limited by `TRANSITIONS`; see
[Events and cancellation](events.md#states).

| Member | Value | Final? |
|---|---|---|
| `QUEUED` | `"queued"` | no |
| `INSPECTING` | `"inspecting"` | no |
| `PREPARING` | `"preparing"` | no |
| `DOWNLOADING` | `"downloading"` | no |
| `PAUSED` | `"paused"` | no |
| `FINALIZING` | `"finalizing"` | no |
| `COMPLETED` | `"completed"` | yes |
| `FAILED` | `"failed"` | yes |
| `CANCELLED` | `"cancelled"` | yes |

## EncryptionMethod

The `METHOD` of an `EXT-X-KEY` tag.

| Member | Value | Supported |
|---|---|---|
| `NONE` | `"NONE"` | nothing to decrypt |
| `AES_128` | `"AES-128"` | yes, with the standard key format |
| `SAMPLE_AES` | `"SAMPLE-AES"` | no; refused before downloading |

## EventType

Kinds of event the engine emits. See [Events and cancellation](events.md#eventtype-reference).

| Member | Value |
|---|---|
| `DOWNLOAD_STARTED` | `"download_started"` |
| `PLAYLIST_LOADED` | `"playlist_loaded"` |
| `STREAM_SELECTED` | `"stream_selected"` |
| `SEGMENT_STARTED` | `"segment_started"` |
| `SEGMENT_COMPLETED` | `"segment_completed"` |
| `SEGMENT_FAILED` | `"segment_failed"` |
| `DOWNLOAD_PROGRESS` | `"download_progress"` |
| `FINALIZATION_STARTED` | `"finalization_started"` |
| `FINALIZATION_COMPLETED` | `"finalization_completed"` |
| `DOWNLOAD_COMPLETED` | `"download_completed"` |
| `DOWNLOAD_FAILED` | `"download_failed"` |
| `DOWNLOAD_CANCELLED` | `"download_cancelled"` |

## OutputFormat

The kind of file the user asks for.

| Member | Value | Meaning |
|---|---|---|
| `AUTO` | `"auto"` | Follow the file name, else the stream's own format |
| `TS` | `"ts"` | An MPEG transport stream file (only for MPEG-TS streams today) |
| `MP4` | `"mp4"` | A fragmented MP4 file (only for fMP4 streams today) |
| `SEGMENTS` | `"segments"` | Keep the segments as separate files in a folder (`segment-00001.ts`, ...) |

## RemuxBackend

Which tool may remux the stream into the requested container.

| Member | Value | Meaning |
|---|---|---|
| `AUTO` | `"auto"` | Use the native muxer, and an installed FFmpeg when it cannot |
| `NATIVE` | `"native"` | Only the built-in muxer |
| `FFMPEG` | `"ffmpeg"` | An FFmpeg already installed (see `OutputConfig.ffmpeg_path`) |

RayoHX remuxes and never transcodes. Remuxing is not available yet, so every download is saved in
the stream's own container, and a request that would need it (such as MPEG-TS into MP4) raises
`OutputFormatError`.

## SegmentState

Where a single segment is in its life cycle.

| Member | Value |
|---|---|
| `PENDING` | `"pending"` |
| `DOWNLOADING` | `"downloading"` |
| `COMPLETED` | `"completed"` |
| `FAILED` | `"failed"` |
| `SKIPPED` | `"skipped"` (an earlier run already had it) |

## StorageStrategy

How segment data moves from the network to the output. See
[Settings](settings.md#storageconfig) for where each one keeps waiting segments.

| Member | Value | Meaning |
|---|---|---|
| `AUTO` | `"auto"` | `DIRECT` when the output can resume, otherwise `STREAMING` |
| `DIRECT` | `"direct"` | Write straight to a resumable file |
| `STREAMING` | `"streaming"` | Write to a pipe or stream; cannot resume |
| `BUFFERED` | `"buffered"` | Hold waiting segments in memory, limited by bytes |
| `TEMPORARY` | `"temporary"` | Hold waiting segments as files in the working folder |
| `HYBRID` | `"hybrid"` | Memory first, then files once the memory limit is reached |

## Examples

Branch on the final state of a download:

```python
from rayohx import DownloadState

match result.state:
    case DownloadState.COMPLETED:
        print("done")
    case DownloadState.CANCELLED:
        print("stopped by the user")
    case DownloadState.FAILED:
        print("failed:", result.error)
```

Read a setting from text, for example a command-line option:

```python
from rayohx.enums import OutputFormat

OutputFormat(args.format.lower())  # raises ValueError for an unknown name
```

List the choices for a help message:

```python
print(", ".join(strategy.value for strategy in StorageStrategy))
# auto, direct, streaming, buffered, temporary, hybrid
```
