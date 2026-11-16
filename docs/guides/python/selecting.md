# Selecting tracks

`select_stream` chooses the video stream, the audio tracks and the subtitle tracks to download
from a master playlist, following a `SelectionConfig`.

[Back to the Python guide](../python.md)

## select_stream

```python
rayohx.select_stream(master: MasterPlaylist, config: SelectionConfig) -> StreamSelection
```

A pure function: the same playlist and settings always give the same answer, and nothing is
fetched. When a wish cannot be met it picks the closest track and records why in `notes`. It does
not raise because of an unmet wish.

```python
import rayohx
from rayohx.config import SelectionConfig

master = rayohx.inspect("https://cdn.example.com/vod/master.m3u8")

choice = rayohx.select_stream(
    master,
    SelectionConfig(
        quality="720p",
        audio_languages=("de", "fr"),
        subtitle_languages=("en",),
    ),
)
print(choice.variant.height)  # 720
print([a.name for a in choice.audio_tracks])  # ['Deutsch']
print([s.name for s in choice.subtitle_tracks])  # ['English']
print(choice.notes)  # ("No audio track is available in 'fr'.",)
```

`select_stream` needs a `MasterPlaylist`. If `inspect` returned a `MediaPlaylist`, there is
nothing to choose: the playlist is the stream.

## StreamSelection

A frozen dataclass.

| Field | Type | Meaning |
|---|---|---|
| `variant` | `Variant` | The chosen video stream |
| `audio_tracks` | `tuple[AudioTrack, ...]` | The chosen audio tracks, in the order asked for |
| `subtitle_tracks` | `tuple[SubtitleTrack, ...]` | The chosen subtitle tracks. Empty unless subtitles were asked for |
| `notes` | `tuple[str, ...]` | Why a wish could not be met, in plain words. Empty when everything was met |

## SelectionConfig

The settings that drive the choice. All fields are keyword-only. See
[Settings](settings.md#selectionconfig) for the table of fields and defaults.

## How the choice is made

| Setting | Behavior |
|---|---|
| `quality="best"` | Largest picture, then bandwidth, average bandwidth, frame rate and codec support. Equal streams: the first listed. |
| `quality="worst"` | The smallest picture, then the lowest bandwidth. |
| `quality="1080p"` | The best stream at or below that size. If every stream is larger, the smallest one. |
| `quality="auto"` | Like `1080p`: sharp without the cost of the largest stream. |
| `max_resolution`, `max_bitrate` | Limits applied before the quality choice. If nothing fits, the smallest stream is used. A stream that does not state its size is never ruled out by a size limit. |
| `audio_languages`, `audio_names` | One track per entry, in the order given. If none is found, the default audio track is used. `en` matches `en-US`, but `en-US` does not match `en-GB`. |
| `subtitle_languages`, `subtitle_names` | Subtitles are off by default. A missing language selects nothing and adds a note. |

Details worth knowing:

- Picture size is the shorter side, so a 720x1280 portrait stream counts as 720p.
- Audio-only streams are skipped when video streams exist.
- Forced tracks are chosen only when nothing else matches or when asked for by name.
- With `video_only=True` no audio or subtitle tracks are chosen at all. `audio_tracks` and
  `subtitle_tracks` are empty and `notes` says "Only the video stream is downloaded; separate audio
  and subtitles are skipped." Use it to download just the video of a stream that keeps its audio in a
  separate track (see [Downloading](downloading.md#what-works-today)).
- Tracks are matched within the audio and subtitle groups the chosen variant refers to
  (`Variant.audio_group` and `Variant.subtitle_group`).

## Examples

The default, best quality:

```python
choice = rayohx.select_stream(master, SelectionConfig())
print(choice.variant.height, choice.variant.uri)
```

Stay under a bandwidth budget (the highest stream at or below 3 Mbit/s):

```python
choice = rayohx.select_stream(master, SelectionConfig(max_bitrate=3_000_000))
print(choice.variant.bandwidth)  # 2800000
```

The smallest file:

```python
choice = rayohx.select_stream(master, SelectionConfig(quality="worst"))
```

English audio, with German as a fallback, and English subtitles by name:

```python
choice = rayohx.select_stream(
    master,
    SelectionConfig(
        audio_languages=("en", "de"),
        subtitle_names=("English",),
    ),
)
```

Choose the video only:

```python
choice = rayohx.select_stream(master, SelectionConfig(video_only=True))
print(choice.audio_tracks, choice.subtitle_tracks)  # () ()
print(
    choice.notes
)  # ('Only the video stream is downloaded; separate audio and subtitles are skipped.',)
```

Show the user what was decided and why:

```python
print(f"Video: {choice.variant.height}p at {choice.variant.bandwidth / 1e6:.1f} Mbit/s")
for track in choice.audio_tracks:
    print(f"Audio: {track.name} ({track.language})")
for track in choice.subtitle_tracks:
    print(f"Subtitles: {track.name} ({track.language})")
for note in choice.notes:
    print(f"Note: {note}")
```

Handle a bad setting early, because a `SelectionConfig` validates itself when it is created:

```python
from rayohx.errors import ConfigurationError

try:
    SelectionConfig(quality="ultra")
except ConfigurationError as exc:
    print(exc.describe())
    # quality 'ultra' is not valid. Use best, worst, auto, or a height such as 1080p.
```
