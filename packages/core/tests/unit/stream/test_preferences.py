"""Codec, dynamic range and frame rate preferences."""

import pytest

from rayohx import Resolution, Variant
from rayohx.config import SelectionConfig
from rayohx.errors import ConfigurationError
from rayohx.stream import select_variant

H264 = Variant(
    uri="a", bandwidth=5_000_000, resolution=Resolution(1920, 1080), codecs=("avc1.640028",)
)
HEVC = Variant(
    uri="b", bandwidth=3_000_000, resolution=Resolution(1920, 1080), codecs=("hvc1.2.4.L120",)
)
HDR = Variant(
    uri="c",
    bandwidth=4_000_000,
    resolution=Resolution(1920, 1080),
    codecs=("hvc1.2.4.L120",),
    video_range="PQ",
    frame_rate=60.0,
)
AV1 = Variant(
    uri="d",
    bandwidth=2_000_000,
    resolution=Resolution(1280, 720),
    codecs=("av01.0.05M.08",),
    frame_rate=30.0,
)
ALL = [H264, HEVC, HDR, AV1]


def pick(variants: list[Variant], **settings: object) -> tuple[str, list[str]]:
    notes: list[str] = []
    chosen = select_variant(variants, SelectionConfig(**settings), notes)  # type: ignore[arg-type]
    return chosen.uri, notes


@pytest.mark.parametrize(
    ("codec", "expected"),
    [("h264", "a"), ("avc", "a"), ("hevc", "c"), ("H265", "c"), ("av1", "d")],
)
def test_codec_preference(codec: str, expected: str) -> None:
    assert pick(ALL, codec=codec)[0] == expected


def test_missing_codec_falls_back_with_a_note() -> None:
    uri, notes = pick(ALL, codec="vp9")
    assert uri == "a"  # the best of everything
    assert any("vp9" in note for note in notes)


def test_video_range_preference() -> None:
    assert pick(ALL, video_range="hdr")[0] == "c"
    assert pick(ALL, video_range="pq")[0] == "c"
    assert pick(ALL, video_range="sdr")[0] == "a"  # streams that say nothing count as SDR
    uri, notes = pick([H264, HEVC], video_range="hlg")
    assert uri == "a"
    assert any("HLG" in note for note in notes)


def test_codec_and_range_combine() -> None:
    assert pick(ALL, codec="hevc", video_range="sdr")[0] == "b"


def test_max_frame_rate_keeps_unstated_rates() -> None:
    assert pick(ALL, max_frame_rate=30)[0] == "a"  # H.264 states none, HDR is 60
    only_fast = [HDR]
    uri, notes = pick(only_fast, max_frame_rate=24)
    assert uri == "c"
    assert any("frame rate" in note for note in notes)


@pytest.mark.parametrize(
    "settings",
    [{"codec": "mpeg2"}, {"video_range": "dolby"}, {"max_frame_rate": 0}],
)
def test_bad_values_are_refused(settings: dict[str, object]) -> None:
    with pytest.raises(ConfigurationError):
        SelectionConfig(**settings)  # type: ignore[arg-type]


def test_variant_cannot_be_combined_with_preferences() -> None:
    with pytest.raises(ConfigurationError, match="codec"):
        SelectionConfig(variant=1, codec="hevc")
