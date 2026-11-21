from datetime import UTC, datetime

import pytest

from rayohx import ContainerFormat, MediaPlaylist, SegmentRange
from rayohx.playlist.parser import parse_playlist
from tests.helpers.hls import BASE, DIR, media


def test_simple_media_playlist() -> None:
    playlist = media("media_simple.m3u8")
    assert playlist.uri == BASE
    assert playlist.version == 3
    assert playlist.target_duration == 10
    assert playlist.is_vod
    assert playlist.playlist_type == "VOD"
    assert playlist.container is ContainerFormat.MPEG_TS
    assert [segment.uri for segment in playlist.segments] == [
        f"{DIR}segment0.ts",
        f"{DIR}segment1.ts",
        f"{DIR}segment2.ts",
    ]
    assert [segment.duration for segment in playlist.segments] == [9.009, 9.009, 3.003]
    assert [segment.title for segment in playlist.segments] == ["First", "", ""]
    assert [segment.sequence_number for segment in playlist.segments] == [0, 1, 2]
    assert [segment.index for segment in playlist.segments] == [0, 1, 2]
    assert playlist.total_duration == pytest.approx(21.021)


def test_absolute_urls_are_kept() -> None:
    uris = [segment.uri for segment in media("media_absolute.m3u8").segments]
    assert uris == [
        "https://cdn.example.net/video/seg-1.ts",
        "http://cdn2.example.net:8080/video/seg-2.ts?auth=abc",
    ]


def test_relative_urls_follow_rfc_3986() -> None:
    uris = [segment.uri for segment in media("media_paths.m3u8").segments]
    assert uris == [
        "https://media.example.com/vod/shared/a.ts",
        "https://media.example.com/root/b.ts",
        "https://other.example.org/c.ts",
        f"{BASE}?part=4",
        f"{DIR}dir/d.ts?x=1&y=2",
    ]


def test_discontinuity_and_program_date_time_apply_to_the_next_segment_only() -> None:
    playlist = media("media_discontinuity.m3u8")
    assert [segment.discontinuity for segment in playlist.segments] == [False, True, False]
    assert playlist.segments[0].program_date_time is None
    assert playlist.segments[1].program_date_time == datetime(
        2026, 1, 2, 3, 4, 5, 250000, tzinfo=UTC
    )
    assert playlist.segments[2].program_date_time is None
    assert playlist.segments[0].sequence_number == 7


def test_byte_ranges_resolve_missing_offsets() -> None:
    playlist = media("media_byterange.m3u8")
    assert [segment.byte_range for segment in playlist.segments] == [
        SegmentRange(1000, 720),
        SegmentRange(2000, 1720),
        SegmentRange(500, 9000),
    ]
    init = playlist.segments[0].init_map
    assert init is not None
    assert init.byte_range == SegmentRange(720, 0)
    assert playlist.container is ContainerFormat.FMP4


def test_webvtt_segments() -> None:
    assert media("media_subtitles.m3u8").container is ContainerFormat.WEBVTT


@pytest.mark.parametrize(
    ("uri", "container"),
    [
        ("a.ts", ContainerFormat.MPEG_TS),
        ("a.TS?x=1", ContainerFormat.MPEG_TS),
        ("a.m4s", ContainerFormat.FMP4),
        ("a.mp4", ContainerFormat.FMP4),
        ("a.cmfv", ContainerFormat.FMP4),
        ("segment", ContainerFormat.UNKNOWN),
        ("a.aac", ContainerFormat.UNKNOWN),
    ],
)
def test_container_detection(uri: str, container: ContainerFormat) -> None:
    text = f"#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:4,\n{uri}\n#EXT-X-ENDLIST\n"
    playlist = parse_playlist(text, BASE)
    assert isinstance(playlist, MediaPlaylist)
    assert playlist.container is container


def test_extinf_without_a_comma_is_accepted() -> None:
    playlist = parse_playlist("#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:4\na.ts\n", BASE)
    assert isinstance(playlist, MediaPlaylist)
    assert playlist.segments[0].duration == 4.0
    assert not playlist.is_vod
