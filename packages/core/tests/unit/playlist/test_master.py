import pytest

from rayohx import MasterPlaylist, Resolution
from rayohx.errors import InvalidPlaylistError
from rayohx.playlist.parser import parse_playlist
from tests.helpers.hls import BASE, DIR, master


def test_basic_master_playlist() -> None:
    playlist = master("master_basic.m3u8")
    assert playlist.version == 6
    assert len(playlist.variants) == 4
    first = playlist.variants[0]
    assert first.uri == f"{DIR}360p/index.m3u8"
    assert first.bandwidth == 800_000
    assert first.average_bandwidth == 700_000
    assert first.resolution == Resolution(640, 360)
    assert first.frame_rate == 25.0
    assert first.codecs == ("avc1.4d401e", "mp4a.40.2")
    last = playlist.variants[3]
    assert last.video_range == "PQ"
    assert last.average_bandwidth is None
    assert last.codecs[0].startswith("hvc1")


def test_absolute_variant_urls_and_names() -> None:
    playlist = master("master_absolute.m3u8")
    assert playlist.variants[0].uri == "https://cdn.example.net/hls/720.m3u8"
    assert playlist.variants[1].uri == "http://cdn2.example.net/hls/1080.m3u8?sig=zz"
    assert playlist.variants[1].name == "Full HD"


def test_audio_and_subtitle_groups() -> None:
    playlist = master("master_audio_subs.m3u8")
    assert [variant.bandwidth for variant in playlist.variants] == [2_000_000, 4_500_000, 64_000]
    assert playlist.variants[0].audio_group == "aud"
    assert playlist.variants[0].subtitle_group == "subs"
    assert [track.name for track in playlist.audio_group("aud")] == [
        "English",
        "English Commentary",
        "Français",
        "Deutsch",
    ]
    english = playlist.audio_tracks[0]
    assert english.default
    assert english.autoselect
    assert english.channels == "2"
    assert english.uri == f"{DIR}audio/en.m3u8"
    assert playlist.audio_tracks[1].characteristics == ("public.accessibility.describes-video",)
    assert [track.language for track in playlist.subtitle_tracks] == ["en", "en", "es"]
    assert playlist.subtitle_tracks[1].forced
    assert playlist.video_tracks == ()


def test_unusual_but_valid_attribute_order_and_spacing() -> None:
    playlist = master("master_attribute_order.m3u8")
    middle, low = playlist.variants
    assert middle.bandwidth == 1_200_000
    assert middle.resolution == Resolution(854, 480)
    assert middle.frame_rate == 29.97
    assert middle.codecs == ("avc1.42e01e", "mp4a.40.2")
    assert middle.name == "a, b = c"
    assert low.bandwidth == 300_000
    assert low.resolution == Resolution(426, 240)
    assert playlist.subtitle_tracks[0].uri == f"{DIR}sub.m3u8"


def test_unknown_tags_comments_and_blank_lines_are_skipped() -> None:
    playlist = master("master_unknown_tags.m3u8")
    assert [variant.uri for variant in playlist.variants] == [f"{DIR}video.m3u8"]


def test_video_renditions() -> None:
    text = (
        '#EXTM3U\n#EXT-X-MEDIA:TYPE=VIDEO,GROUP-ID="v",NAME="Angle 2",DEFAULT=YES,URI="a2.m3u8"\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=1000,VIDEO="v"\nmain.m3u8\n'
    )
    playlist = parse_playlist(text, BASE)
    assert isinstance(playlist, MasterPlaylist)
    assert playlist.video_tracks[0].name == "Angle 2"
    assert playlist.video_tracks[0].default
    assert playlist.variants[0].video_group == "v"


@pytest.mark.parametrize(
    "tag",
    [
        "#EXT-X-STREAM-INF:BANDWIDTH=abc",
        "#EXT-X-STREAM-INF:BANDWIDTH=1,RESOLUTION=big",
        "#EXT-X-STREAM-INF:BANDWIDTH=1,FRAME-RATE=fast",
        "#EXT-X-STREAM-INF:BANDWIDTH=1,FRAME-RATE=-1",
    ],
)
def test_bad_variant_attributes_are_invalid(tag: str) -> None:
    with pytest.raises(InvalidPlaylistError):
        parse_playlist(f"#EXTM3U\n{tag}\none.m3u8\n", BASE)


@pytest.mark.parametrize(
    "tag",
    [
        '#EXT-X-MEDIA:GROUP-ID="a",NAME="x"',
        '#EXT-X-MEDIA:TYPE=AUDIO,NAME="x"',
        '#EXT-X-MEDIA:TYPE=DATA,GROUP-ID="a",NAME="x"',
    ],
)
def test_bad_media_tags_are_invalid(tag: str) -> None:
    text = f"#EXTM3U\n{tag}\n#EXT-X-STREAM-INF:BANDWIDTH=1\none.m3u8\n"
    with pytest.raises(InvalidPlaylistError):
        parse_playlist(text, BASE)
