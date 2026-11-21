from collections.abc import Callable

import pytest

from rayohx import ContainerFormat
from rayohx._http._response import HttpResponse
from rayohx.downloader._stream import (
    audio_codecs,
    describe,
    first_segment,
    kind,
    load_media,
    probe_container,
    require_single_stream,
)
from rayohx.errors import InvalidPlaylistError, OutputFormatError, UnsupportedPlaylistError
from rayohx.models import AudioTrack, MasterPlaylist, MediaPlaylist, SubtitleTrack
from rayohx.playlist import parse_playlist
from rayohx.stream import StreamSelection
from tests.helpers.media import BASE, fmp4_init, ts_payload
from tests.helpers.mux import media

MASTER_TEXT = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360,CODECS="avc1.42e01e,mp4a.40.2"
low.m3u8
"""


class FakeClient:
    """Serves playlist text and segment bytes from dictionaries, by absolute address."""

    def __init__(self, texts: dict[str, str] | None = None, files: dict[str, bytes] | None = None):
        self.texts = texts or {}
        self.files = files or {}
        self.fetched: list[str] = []

    def fetch_text(self, url: str) -> tuple[str, str]:
        return self.texts[url], url

    def fetch_bytes(
        self,
        url: str,
        *,
        byte_range: object = None,
        max_bytes: int = 0,
        on_bytes: Callable[[int], None] | None = None,
    ) -> HttpResponse:
        self.fetched.append(url)
        return HttpResponse(url=url, status_code=200, headers={}, content=self.files[url])


def media_playlist(*names: str) -> MediaPlaylist:
    lines = ["#EXTM3U", "#EXT-X-TARGETDURATION:2", "#EXT-X-PLAYLIST-TYPE:VOD"]
    for name in names:
        lines += ["#EXTINF:2,", name]
    lines.append("#EXT-X-ENDLIST")
    playlist = parse_playlist("\n".join(lines) + "\n", BASE + "index.m3u8")
    assert isinstance(playlist, MediaPlaylist)
    return playlist


def master_playlist() -> MasterPlaylist:
    playlist = parse_playlist(MASTER_TEXT, BASE + "master.m3u8")
    assert isinstance(playlist, MasterPlaylist)
    return playlist


def audio_track() -> AudioTrack:
    return AudioTrack(
        group_id="aud",
        name="English",
        language="en",
        uri=BASE + "en.m3u8",
        default=True,
        autoselect=True,
        forced=False,
        channels="2",
        characteristics=(),
    )


def subtitle_track() -> SubtitleTrack:
    return SubtitleTrack(
        group_id="sub",
        name="English",
        language="en",
        uri=BASE + "en-sub.m3u8",
        default=False,
        autoselect=True,
        forced=False,
        characteristics=(),
    )


def test_a_playlist_is_called_master_or_media() -> None:
    assert kind(master_playlist()) == "master"
    assert kind(media_playlist("a.ts")) == "media"


def test_a_selection_is_described_for_events() -> None:
    selection = StreamSelection(
        variant=master_playlist().variants[0],
        audio_tracks=(audio_track(),),
        subtitle_tracks=(subtitle_track(),),
        notes=("a fallback was used",),
    )
    assert describe(selection) == {
        "bandwidth": 800000,
        "resolution": "640x360",
        "codecs": ["avc1.42e01e", "mp4a.40.2"],
        "audio": ["English"],
        "subtitles": ["English"],
        "notes": ["a fallback was used"],
    }


def test_a_stream_without_a_picture_size_is_described_without_one() -> None:
    text = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=64000\naudio.m3u8\n"
    playlist = parse_playlist(text, BASE + "master.m3u8")
    assert isinstance(playlist, MasterPlaylist)
    described = describe(StreamSelection(variant=playlist.variants[0]))
    assert described["resolution"] is None
    assert described["codecs"] == []


def test_a_media_playlist_is_fetched_and_parsed() -> None:
    url = BASE + "low.m3u8"
    client = FakeClient(texts={url: "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:2,\na.ts\n"})
    playlist = load_media(client, url)  # type: ignore[arg-type]
    assert isinstance(playlist, MediaPlaylist)
    assert [segment.uri for segment in playlist.segments] == [BASE + "a.ts"]


def test_a_media_playlist_gets_the_variables_of_its_master() -> None:
    url = BASE + "low.m3u8"
    text = (
        '#EXTM3U\n#EXT-X-DEFINE:IMPORT="host"\n#EXT-X-TARGETDURATION:2\n#EXTINF:2,\n'
        "https://{$host}/a.ts\n"
    )
    client = FakeClient(texts={url: text})
    playlist = load_media(client, url, {"host": "cdn.example.com"})  # type: ignore[arg-type]
    assert [segment.uri for segment in playlist.segments] == ["https://cdn.example.com/a.ts"]


def test_an_imported_variable_without_a_master_is_refused() -> None:
    url = BASE + "low.m3u8"
    text = '#EXTM3U\n#EXT-X-DEFINE:IMPORT="host"\n#EXT-X-TARGETDURATION:2\n#EXTINF:2,\na.ts\n'
    client = FakeClient(texts={url: text})
    with pytest.raises(UnsupportedPlaylistError, match="imports"):
        load_media(client, url)  # type: ignore[arg-type]


def test_something_that_is_not_a_playlist_is_explained() -> None:
    url = BASE + "low.m3u8"
    client = FakeClient(texts={url: "<html>sign in</html>"})
    with pytest.raises(InvalidPlaylistError, match="did not return an HLS playlist") as info:
        load_media(client, url)  # type: ignore[arg-type]
    assert info.value.hint


def test_a_master_playlist_where_a_media_playlist_is_expected_is_refused() -> None:
    url = BASE + "low.m3u8"
    client = FakeClient(texts={url: MASTER_TEXT})
    with pytest.raises(InvalidPlaylistError, match="Expected a playlist of segments"):
        load_media(client, url)  # type: ignore[arg-type]


def test_no_selection_and_a_plain_video_stream_need_no_merging() -> None:
    require_single_stream(None)
    require_single_stream(StreamSelection(variant=master_playlist().variants[0]))


def test_a_separate_audio_track_cannot_be_merged_yet() -> None:
    selection = StreamSelection(
        variant=master_playlist().variants[0], audio_tracks=(audio_track(),)
    )
    with pytest.raises(OutputFormatError, match="'English'") as info:
        require_single_stream(selection)
    assert "video_only" in (info.value.hint or "")


def test_subtitles_cannot_be_saved_yet() -> None:
    selection = StreamSelection(
        variant=master_playlist().variants[0], subtitle_tracks=(subtitle_track(),)
    )
    with pytest.raises(OutputFormatError, match="Saving subtitles is not available"):
        require_single_stream(selection)


def test_the_first_segment_is_downloaded_on_its_own() -> None:
    playlist = media_playlist("a.bin", "b.bin")
    client = FakeClient(files={BASE + "a.bin": b"first", BASE + "b.bin": b"second"})
    data = first_segment(client, playlist)  # type: ignore[arg-type]
    assert (data.index, data.media) == (0, b"first")
    assert client.fetched == [BASE + "a.bin"]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (ts_payload(1, 3), ContainerFormat.MPEG_TS),
        (fmp4_init(), ContainerFormat.FMP4),
        (b"<html>denied</html>", ContainerFormat.UNKNOWN),
    ],
)
def test_the_format_is_found_by_looking_at_the_first_segment(
    data: bytes, expected: ContainerFormat
) -> None:
    playlist = media_playlist("a.bin")
    client = FakeClient(files={BASE + "a.bin": data})
    assert probe_container(client, playlist) is expected  # type: ignore[arg-type]


def test_a_playlist_without_segments_has_nothing_to_look_at() -> None:
    playlist = media_playlist()
    client = FakeClient()
    assert probe_container(client, playlist) is ContainerFormat.UNKNOWN  # type: ignore[arg-type]
    assert client.fetched == []


def test_the_audio_codecs_of_a_transport_stream_are_listed() -> None:
    playlist = media_playlist("a.ts")
    client = FakeClient(files={BASE + "a.ts": media("h264_aac.ts")})
    codecs = audio_codecs(client, playlist, ContainerFormat.MPEG_TS)  # type: ignore[arg-type]
    assert codecs == ("aac",)


def test_fragmented_mp4_needs_no_fix_so_it_is_not_even_downloaded() -> None:
    playlist = media_playlist("a.m4s")
    client = FakeClient()
    assert audio_codecs(client, playlist, ContainerFormat.FMP4) == ()  # type: ignore[arg-type]
    assert client.fetched == []
