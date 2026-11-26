# Inspecting streams

Looking at a stream means fetching and parsing its playlist without downloading any media. The
result is a typed, frozen object you can read, filter and pass to
[`select_stream`](selecting.md).

[Back to the Python guide](../python.md) · To download a stream, see [Downloading](downloading.md).

| Function | Module | Returns |
|---|---|---|
| [`inspect(url, network=None)`](#inspect) | `rayohx` | `MasterPlaylist` or `MediaPlaylist` |
| [`inspect_playlist(url, fetcher)`](#inspect_playlist) | `rayohx` | `MasterPlaylist` or `MediaPlaylist` |
| [`inspect_text(text, base_url)`](#inspect_text) | `rayohx` | `MasterPlaylist` or `MediaPlaylist` |
| [`parse_playlist(text, uri)`](#parse_playlist) | `rayohx` | `MasterPlaylist` or `MediaPlaylist` |
| [`is_hls_playlist(text)`](#is_hls_playlist) | `rayohx` | `bool` |
| [`parse_attribute_list(text, *, line=None)`](#parse_attribute_list) | `rayohx.playlist` | `dict[str, str]` |
| [`PlaylistFetcher`](#playlistfetcher) | `rayohx` | a protocol |

## inspect

```python
rayohx.inspect(url: str, network: NetworkConfig | None = None) -> Playlist
```

Fetches the playlist at `url`, follows redirects, parses it and returns the typed result. It
creates and closes its own HTTP client, so there is nothing to clean up.

| Parameter | Meaning |
|---|---|
| `url` | An absolute `http` or `https` address |
| `network` | Headers, cookies, proxy, timeouts, retries and TLS for the request. Defaults to `NetworkConfig()` |

```python
import rayohx
from rayohx.config import NetworkConfig

playlist = rayohx.inspect("https://cdn.example.com/vod/master.m3u8")
```

With request settings, for a stream behind a login:

```python
network = NetworkConfig(
    headers={"Referer": "https://site.example/", "Authorization": "Bearer ..."},
    cookies={"session": "..."},
    connect_timeout=5,
    retries=2,
)
playlist = rayohx.inspect("https://cdn.example.com/vod/master.m3u8", network)
```

The result is a `MasterPlaylist` when the address lists several streams and a `MediaPlaylist` when
it lists segments. Check which you got:

```python
from rayohx.models import MasterPlaylist

if isinstance(playlist, MasterPlaylist):
    print(len(playlist.variants), "streams")
else:
    print(playlist.segment_count, "segments,", playlist.total_duration, "seconds")
```

Possible errors:

| Error | When |
|---|---|
| `ConfigurationError` | The URL is not an absolute http(s) address, or a setting is invalid |
| `PlaylistNotFoundError` | The server answers 404 or 410 |
| `AuthenticationError` | The server answers 401 or 403 |
| `InvalidPlaylistError` | The response is not an HLS playlist, for example a web page |
| `UnsupportedPlaylistError` | The playlist uses a feature RayoHX refuses (see [parsing rules](#parsing-rules)) |
| `NetworkError` and subclasses | Connection, timeout, TLS, redirect or bad-response failures |

See [Errors](errors.md) for the full hierarchy.

## inspect_playlist

```python
rayohx.inspect_playlist(url: str, fetcher: PlaylistFetcher) -> Playlist
```

`inspect` with your own transport. It validates `url`, asks `fetcher` for the text, checks that it
is a playlist and parses it against the address the text finally came from.

Use it when requests must go through an existing session or cache, or in tests.

```python
class CachedFetcher:
    def __init__(self, texts: dict[str, str]) -> None:
        self.texts = texts

    def fetch_text(self, url: str) -> tuple[str, str]:
        return self.texts[url], url


fetcher = CachedFetcher({"https://cdn.example.com/vod/360p/index.m3u8": media_text})
playlist = rayohx.inspect_playlist("https://cdn.example.com/vod/360p/index.m3u8", fetcher)
```

Errors: `ConfigurationError` for a bad address, `InvalidPlaylistError` when the text is not a
playlist (the error carries a hint to check the address, headers and cookies).

## inspect_text

```python
rayohx.inspect_text(text: str, base_url: str) -> Playlist
```

Parses playlist text you already have, for example one read from a file, without any request.
Relative addresses in it are resolved against `base_url`, which must be an http(s) address.

```python
text = Path("master.m3u8").read_text()
playlist = rayohx.inspect_text(text, "https://cdn.example.com/vod/master.m3u8")
```

Errors: `ConfigurationError` for a bad `base_url`, `InvalidPlaylistError` when the text is not a
playlist.

## PlaylistFetcher

A `typing.Protocol`: anything with one method.

```python
class PlaylistFetcher(Protocol):
    def fetch_text(self, url: str) -> tuple[str, str]: ...
```

`fetch_text(url)` returns `(text, final_url)`, where `final_url` is the address the text finally
came from after redirects. Relative addresses in the playlist are resolved against `final_url`, so
report it correctly.

## parse_playlist

```python
rayohx.parse_playlist(text: str, uri: str) -> Playlist
```

Parses playlist text and makes every address absolute against `uri`, using RFC 3986 rules.
Pass the address the text actually came from, after redirects.

```python
text = open("master.m3u8", encoding="utf-8").read()
playlist = rayohx.parse_playlist(text, "https://cdn.example.com/vod/master.m3u8")
print(playlist.variants[0].uri)  # https://cdn.example.com/vod/360p/index.m3u8
```

A media playlist:

```python
media = rayohx.parse_playlist(media_text, "https://cdn.example.com/vod/360p/index.m3u8")
print(media.segment_count, media.total_duration, media.is_vod)  # 3 15.5 True
print(media.segments[0].uri)  # https://cdn.example.com/vod/360p/seg0.ts
print(media.segments[0].sequence_number)  # 0
print(media.container)  # ContainerFormat.MPEG_TS
```

Errors name the line. A web page or other non-playlist raises `InvalidPlaylistError`:

```python
from rayohx.errors import InvalidPlaylistError

try:
    rayohx.parse_playlist("<html>nope</html>", "https://x/y")
except InvalidPlaylistError as exc:
    print(exc.describe())
    # This is not an HLS playlist: it does not start with #EXTM3U. Check that the address
    # points to an .m3u8 playlist and not to a web page.
```

### Parsing rules

- A playlist is recognised by its `#EXTM3U` header, never by its file name or address.
- Tags the parser does not know are skipped, so newer playlists keep working.
- Playlist variables (`EXT-X-DEFINE`) are replaced for you, so every address you see is final. The
  master playlist's variables are on `MasterPlaylist.variables`.
- I-frame-only playlists raise `UnsupportedPlaylistError`, because ignoring them would produce
  wrong video.
- Segment and playlist addresses must be `http` or `https`. Key addresses may use another scheme,
  so a SAMPLE-AES or DRM playlist can still be inspected. The key is marked unsupported
  (`EncryptionInfo.is_supported` is `False`) and a download refuses it later.
- A key without an `IV` keeps `iv=None`. The IV is derived from the segment's `sequence_number`
  when decrypting, as the HLS specification says.
- An `EXT-X-BYTERANGE` without an offset continues from the previous range of the same file
  (`SegmentRange.offset` is filled in).
- The container (`MPEG_TS`, `FMP4`, `WEBVTT`) is guessed from the playlist. When it is unclear it
  stays `UNKNOWN` and the first bytes of a segment settle it later.

## is_hls_playlist

```python
rayohx.is_hls_playlist(text: str) -> bool
```

Whether `text` starts like an HLS playlist, whatever it was called or fetched from. Use it to avoid
parsing a web page or an error body:

```python
text = response_body.decode("utf-8", errors="replace")
if rayohx.is_hls_playlist(text):
    playlist = rayohx.parse_playlist(text, final_url)
else:
    print("Not an HLS playlist")
```

## parse_attribute_list

```python
rayohx.playlist.parse_attribute_list(text: str, *, line: int | None = None) -> dict[str, str]
```

Splits `KEY=value,KEY="quoted, value"` into a dictionary, in any order. Quotes are removed from
quoted values. `line` is only used to name the line in an error. Raises `InvalidPlaylistError` if
the list is malformed.

```python
from rayohx.playlist import parse_attribute_list

attributes = parse_attribute_list(
    'BANDWIDTH=800000,RESOLUTION=640x360,CODECS="avc1.4d401e,mp4a.40.2"'
)
print(attributes["CODECS"])  # avc1.4d401e,mp4a.40.2
```

## Examples

Print a table of the streams in a master playlist, best first:

```python
master = rayohx.inspect("https://cdn.example.com/vod/master.m3u8")

for variant in sorted(master.variants, key=lambda v: v.bandwidth, reverse=True):
    size = f"{variant.resolution.width}x{variant.resolution.height}" if variant.resolution else "?"
    print(f"{size:>10}  {variant.bandwidth / 1_000_000:.1f} Mbit/s  {variant.uri}")
#  1920x1080  5.0 Mbit/s  https://cdn.example.com/vod/1080p/index.m3u8
#   1280x720  2.8 Mbit/s  https://cdn.example.com/vod/720p/index.m3u8
#    640x360  0.8 Mbit/s  https://cdn.example.com/vod/360p/index.m3u8
```

List the audio and subtitle languages on offer:

```python
print([(a.language, a.name, a.default) for a in master.audio_tracks])
print([s.language for s in master.subtitle_tracks])
```

Find the tracks that belong to one stream (its group):

```python
variant = master.variants[1]
audio = master.audio_group(variant.audio_group) if variant.audio_group else ()
```

Check a media playlist for encryption before you plan anything:

```python
media = rayohx.inspect("https://cdn.example.com/vod/360p/index.m3u8")
encrypted = [s for s in media.segments if s.encryption is not None]
unsupported = [s for s in encrypted if not s.encryption.is_supported]
if unsupported:
    print("This stream uses DRM or SAMPLE-AES and cannot be downloaded.")
```

Estimate a download's size from a variant:

```python
variant = master.variants[1]
seconds = rayohx.inspect(variant.uri).total_duration
print(f"about {variant.bandwidth * seconds / 8 / 1_000_000:.0f} MB")
```
