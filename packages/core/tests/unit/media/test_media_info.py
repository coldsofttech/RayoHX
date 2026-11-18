"""Media intelligence: codec names, size estimates, what a stream offers and what it needs."""

from pathlib import Path

import httpx
import pytest

from rayohx import OutputFormat
from rayohx.capabilities import Capabilities
from rayohx.config import NetworkConfig, SelectionConfig
from rayohx.media import (
    MediaInfo,
    check_compatibility,
    describe_codec,
    estimate_size,
    inspect_media,
    parse_probe,
)
from rayohx.models import Segment, SegmentRange, Variant
from rayohx.models.playlist import MediaPlaylist
from tests.unit._mux.helpers import MEDIA, Site, hls_site, needs_ffmpeg, single_file_site

BASE = "https://media.example.com/"
NETWORK = NetworkConfig(retries=0, backoff_factor=0.001)
WITH = Capabilities(ffmpeg=Path("/usr/bin/ffmpeg"))
WITHOUT = Capabilities()


@pytest.mark.parametrize(
    ("text", "kind", "codec", "label", "profile", "level"),
    [
        ("avc1.640028", "video", "h264", "H.264 High@4.0", "High", "4.0"),
        ("avc1.4D401F", "video", "h264", "H.264 Main@3.1", "Main", "3.1"),
        ("avc1.42E01E", "video", "h264", "H.264 Baseline@3.0", "Baseline", "3.0"),
        ("hvc1.2.4.L120.B0", "video", "hevc", "HEVC Main 10@4.0", "Main 10", "4.0"),
        ("hev1.1.6.L93.B0", "video", "hevc", "HEVC Main@3.1", "Main", "3.1"),
        ("dvh1.05.06", "video", "dolby-vision", "Dolby Vision 5", "5", None),
        ("vp09.00.41.08", "video", "vp9", "VP9@4.1", "0", "4.1"),
        ("av01.0.08M.08", "video", "av1", "AV1 Main", "Main", "4.0"),
        ("mp4a.40.2", "audio", "aac", "AAC-LC", "AAC-LC", None),
        ("mp4a.40.5", "audio", "aac", "HE-AAC", "HE-AAC", None),
        ("mp4a.40.34", "audio", "mp3", "MP3", "MP3", None),
        ("mp4a.6B", "audio", "mp3", "MP3", None, None),
        ("ac-3", "audio", "ac3", "Dolby Digital", None, None),
        ("ec-3", "audio", "eac3", "Dolby Digital Plus", None, None),
        ("opus", "audio", "opus", "Opus", None, None),
        ("wvtt", "subtitle", "webvtt", "WebVTT", None, None),
        ("zzzz.1", "other", "zzzz", "zzzz.1", None, None),
    ],
)
def test_codec_strings_are_read(
    text: str, kind: str, codec: str, label: str, profile: str | None, level: str | None
) -> None:
    found = describe_codec(text)
    assert (found.kind, found.codec, found.label, found.profile, found.level) == (
        kind, codec, label, profile, level,
    )  # fmt: skip


# --- size --------------------------------------------------------------------------------------


def playlist(*, ranges: bool = False, vod: bool = True, count: int = 4) -> MediaPlaylist:
    segments = tuple(
        Segment(
            index=i,
            uri=f"s{i}.ts",
            duration=10.0,
            sequence_number=i,
            byte_range=SegmentRange(1000, i * 1000) if ranges else None,
        )
        for i in range(count)
    )
    return MediaPlaylist(uri=BASE + "i.m3u8", segments=segments, target_duration=10, end_list=vod)


def variant(**kw: object) -> Variant:
    return Variant(uri="v.m3u8", bandwidth=int(kw.pop("bandwidth", 800_000)), **kw)  # type: ignore[arg-type]


def test_a_live_stream_has_no_size() -> None:
    size = estimate_size(playlist(vod=False), variant(), 0)
    assert (size.kind, size.bytes) == ("unavailable", None)
    assert "live" in size.basis


def test_byte_ranges_give_an_exact_size() -> None:
    size = estimate_size(playlist(ranges=True), variant(), 0)
    assert (size.kind, size.bytes) == ("exact", 4000)


def test_bandwidth_gives_an_estimate_that_says_what_it_is() -> None:
    average = estimate_size(playlist(), variant(average_bandwidth=400_000), 0)
    assert (average.kind, average.bytes) == ("estimated", 400_000 * 40 // 8)
    assert "average" in average.basis
    peak = estimate_size(playlist(), variant(), 0)
    assert peak.bytes == 800_000 * 40 // 8
    assert "upper bound" in peak.basis
    with_audio = estimate_size(playlist(ranges=True), variant(average_bandwidth=400_000), 2)
    assert with_audio.kind == "estimated"  # byte ranges only cover the video
    assert with_audio.bytes == (400_000 + 2 * 128_000) * 40 // 8
    assert "assumed" in with_audio.basis


def test_no_bit_rate_means_no_estimate() -> None:
    assert estimate_size(playlist(), variant(bandwidth=0), 0).kind == "unavailable"
    assert estimate_size(playlist(), None, 0).kind == "unavailable"
    assert estimate_size(playlist(count=0), variant(), 0).kind == "unavailable"


# --- inspecting a stream -----------------------------------------------------------------------


def info_of(site: Site, path: str, **kw: object) -> MediaInfo:
    return inspect_media(
        BASE + path,
        network=NETWORK,
        transport=httpx.MockTransport(site),
        **kw,  # type: ignore[arg-type]
    )


def test_a_master_playlist_without_probing_says_only_what_the_playlist_says() -> None:
    found = info_of(hls_site("ts", "ts"), "ts/master.m3u8", probe=False)
    assert (found.kind, found.container, found.live, found.segment_count) == (
        "master",
        "MPEG-TS",
        False,
        2,
    )
    assert found.duration is not None
    assert found.duration > 0
    assert found.video is not None
    assert (found.video.width, found.video.height, found.video.source) == (320, 240, "playlist")
    assert found.video.codec == "h264"
    assert found.video.pixel_format is None  # nothing is guessed
    assert [(v.index, v.selected) for v in found.variants] == [(1, True)]
    assert found.size.kind == "estimated"
    audio = found.audio[0]
    assert (audio.separate, audio.selected, audio.language, audio.name) == (
        True,
        True,
        "eng",
        "audio_1",
    )
    assert audio.codec == "aac"


@needs_ffmpeg
def test_probing_the_first_segment_fills_in_the_details() -> None:
    found = info_of(single_file_site("h264_aac.ts"), "show/index.m3u8")
    assert found.kind == "media"
    assert found.video is not None
    assert (found.video.codec, found.video.width, found.video.height) == ("h264", 320, 240)
    assert found.video.source == "probe"
    assert found.video.profile
    assert found.video.pixel_format == "yuv420p"
    assert found.video.frame_rate == pytest.approx(25, abs=1)
    audio = found.audio[0]
    assert (audio.codec, audio.source, audio.selected) == ("aac", "probe", True)
    assert audio.channels
    assert audio.sample_rate
    data = found.to_dict()
    assert data["video"]["source"] == "probe"
    assert data["size"]["kind"] in {"estimated", "unavailable"}


def test_without_ffprobe_the_answer_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rayohx.media.info.find_ffprobe", lambda _p=None: None)
    found = info_of(single_file_site("h264_aac.ts"), "show/index.m3u8")
    assert any("ffprobe is not installed" in n for n in found.notes)
    assert found.video is None or found.video.source == "playlist"


def test_selection_decides_what_is_marked_selected() -> None:
    master = (
        "#EXTM3U\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="a",NAME="English",LANGUAGE="en",DEFAULT=YES,URI="en.m3u8"\n'
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="a",NAME="Deutsch",LANGUAGE="de",URI="de.m3u8"\n'
        '#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="s",NAME="English",LANGUAGE="en",URI="sub.m3u8"\n'
        "#EXT-X-STREAM-INF:BANDWIDTH=900000,AVERAGE-BANDWIDTH=700000,RESOLUTION=1280x720,"
        'FRAME-RATE=29.97,CODECS="avc1.640028,mp4a.40.2",AUDIO="a",SUBTITLES="s"\nhi.m3u8\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=300000,RESOLUTION=640x360,CODECS="avc1.42E01E,mp4a.40.2",'
        'AUDIO="a",SUBTITLES="s"\nlo.m3u8\n'
    )
    page = "#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:4,\nseg.ts\n#EXT-X-ENDLIST\n"
    web = Site(
        {
            "s/master.m3u8": master.encode(),
            **{f"s/{n}.m3u8": page.encode() for n in ("hi", "lo", "en", "de", "sub")},
        }
    )
    default = info_of(web, "s/master.m3u8", probe=False)
    assert [a.name for a in default.audio if a.selected] == ["English"]
    assert [s.name for s in default.subtitles if s.selected] == []
    german = info_of(
        web, "s/master.m3u8", probe=False,
        selection=SelectionConfig(
            quality="worst", audio_languages=("de",), subtitle_languages=("en",)
        ),
    )  # fmt: skip
    assert [a.name for a in german.audio if a.selected] == ["Deutsch"]
    assert [s.name for s in german.subtitles if s.selected] == ["English"]
    assert [v.selected for v in german.variants] == [False, True]
    assert german.video is not None
    assert (german.video.height, german.video.label) == (360, "H.264 Baseline@3.0")
    hi = default.video
    assert hi is not None
    assert (hi.frame_rate, hi.label, hi.bit_rate) == (29.97, "H.264 High@4.0", 700_000)


def test_secrets_in_the_address_are_never_returned() -> None:
    found = info_of(hls_site("ts", "ts"), "ts/master.m3u8?token=SECRET", probe=False)
    assert "SECRET" not in str(found.to_dict())


def test_a_bad_address_is_a_configuration_error() -> None:
    from rayohx.errors import ConfigurationError

    with pytest.raises(ConfigurationError):
        inspect_media("ftp://nope")


# --- compatibility -----------------------------------------------------------------------------


def levels(found: MediaInfo, fmt: OutputFormat, caps: Capabilities) -> list[tuple[str, str]]:
    return [(n.level, n.message) for n in check_compatibility(found, fmt, caps)]


def test_formats_that_need_ffmpeg_are_flagged_without_it() -> None:
    found = info_of(hls_site("ts", "ts"), "ts/master.m3u8", probe=False)
    for fmt in (OutputFormat.MKV, OutputFormat.AUDIO):
        assert levels(found, fmt, WITHOUT)[0][0] == "error"
        assert "needs FFmpeg" in levels(found, fmt, WITHOUT)[0][1]
        assert not [n for n in levels(found, fmt, WITH) if n[0] == "error"]


def test_separate_audio_rules() -> None:
    found = info_of(hls_site("ts", "ts"), "ts/master.m3u8", probe=False)
    assert any("separate audio" in m for _, m in levels(found, OutputFormat.ORIGINAL, WITH))
    assert any("separate audio" in m.lower() for _, m in levels(found, OutputFormat.SEGMENTS, WITH))
    assert not levels(found, OutputFormat.MP4, WITH)


def test_an_mp4_needs_ffmpeg_for_codecs_the_built_in_remuxer_cannot_copy() -> None:
    found = info_of(single_file_site("h264_aac.ts"), "show/index.m3u8", probe=False)
    odd = MediaInfo(
        **{**{f: getattr(found, f) for f in found.__slots__}, "video": found.video}  # type: ignore[arg-type]
    )
    from dataclasses import replace

    from rayohx.media import AudioInfo, VideoInfo

    mp2 = replace(odd, video=VideoInfo(codec="mpeg2video"), audio=(AudioInfo(codec="mp2"),))
    assert levels(mp2, OutputFormat.MP4, WITH)[0][0] == "warning"
    assert levels(mp2, OutputFormat.MP4, WITHOUT)[0][0] == "error"
    assert "mpeg2video" in levels(mp2, OutputFormat.MP4, WITHOUT)[0][1]
    assert levels(mp2, OutputFormat.TS, WITHOUT) == []


def test_live_and_encrypted_streams_are_refused() -> None:
    from dataclasses import replace

    base = info_of(single_file_site("h264_aac.ts"), "show/index.m3u8", probe=False)
    assert levels(replace(base, live=True), OutputFormat.AUTO, WITH)[0][0] == "error"
    assert (
        "SAMPLE-AES"
        in levels(replace(base, encryption="SAMPLE-AES"), OutputFormat.AUTO, WITH)[0][1]
    )


def test_fragmented_mp4_cannot_be_saved_as_ts() -> None:
    found = info_of(hls_site("fmp4", "f"), "f/v0.m3u8", probe=False)
    assert found.container == "fragmented MP4"
    assert any("cannot be saved as TS" in m for _, m in levels(found, OutputFormat.TS, WITH))


def test_probe_output_is_parsed() -> None:
    text = (
        '{"format": {"format_name": "mpegts", "duration": "3.9", "size": "100", "bit_rate": "200",'
        ' "tags": {"TITLE": "x"}}, "streams": ['
        '{"index": 0, "codec_type": "video", "codec_name": "h264", "profile": "High", "level": 40,'
        ' "width": 320, "height": 240, "avg_frame_rate": "25/1", "pix_fmt": "yuv420p"},'
        '{"index": 1, "codec_type": "audio", "codec_name": "aac", "channels": 2,'
        ' "sample_rate": "44100", "tags": {"language": "eng"}},'
        '{"index": 2, "codec_type": "video", "codec_name": "png",'
        ' "disposition": {"attached_pic": 1}}]}'
    )
    info = parse_probe(text)
    assert (info.format_name, info.duration, info.size_bytes) == ("mpegts", 3.9, 100)
    assert info.tags == {"title": "x"}
    video = info.of_kind("video")
    assert len(video) == 1  # a cover picture is not a video stream
    assert (video[0].frame_rate, video[0].level, video[0].pixel_format) == (25.0, 40, "yuv420p")
    assert info.of_kind("audio")[0].language == "eng"
    assert MEDIA.exists()
