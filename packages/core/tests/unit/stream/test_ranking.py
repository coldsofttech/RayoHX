import pytest

from rayohx import Variant
from rayohx.stream._ranking import (
    best_key,
    closest_to,
    codec_rank,
    describe,
    describe_full,
    is_audio_only,
    worst_key,
)
from tests.helpers.hls import variant


@pytest.mark.parametrize(
    ("codecs", "rank"),
    [
        (("avc1.640028",), 4),
        (("hvc1.2.4.L120",), 3),
        (("hev1.1.6.L93",), 3),
        (("vp09.00.10.08",), 2),
        (("av01.0.04M.08",), 1),
        (("AVC1.640028",), 4),
        (("mp4a.40.2", "avc1.640028"), 4),  # the audio codec is skipped, the video one counts
        (("mp4a.40.2",), 0),
        ((), 0),
    ],
)
def test_widely_playable_codecs_rank_higher(codecs: tuple[str, ...], rank: int) -> None:
    assert codec_rank(variant(1000, (1280, 720), *codecs)) == rank


@pytest.mark.parametrize(
    ("size", "codecs", "expected"),
    [
        (None, ("mp4a.40.2",), True),
        (None, ("ac-3",), True),
        (None, ("avc1.640028", "mp4a.40.2"), False),
        (None, ("dvh1.05.06",), False),
        ((1280, 720), ("mp4a.40.2",), False),  # a picture size means there is video
        (None, (), False),  # nothing is known, so it is not assumed to be audio
    ],
)
def test_a_stream_is_audio_only_when_it_has_no_picture_and_no_video_codec(
    size: tuple[int, int] | None, codecs: tuple[str, ...], expected: bool
) -> None:
    assert is_audio_only(variant(64000, size, *codecs)) is expected


def test_the_best_key_ranks_height_then_bandwidth_then_average_then_rate_then_codec() -> None:
    stream = variant(2000, (1280, 720), "avc1.640028", average_bandwidth=1800, frame_rate=30.0)
    assert best_key((0, stream)) == (720, 2000, 1800, 30.0, 4, 0)


def test_missing_figures_count_as_zero_in_the_best_key() -> None:
    assert best_key((2, variant(500))) == (0, 500, 0, 0.0, 0, -2)


def test_an_earlier_listed_copy_ranks_higher() -> None:
    stream = variant(1000, (1280, 720), "avc1.640028")
    assert best_key((0, stream)) > best_key((1, stream))


def test_the_best_key_prefers_height_over_bandwidth() -> None:
    sharp = variant(1000, (1920, 1080))
    heavy = variant(9000, (1280, 720))
    assert best_key((0, sharp)) > best_key((1, heavy))


def test_the_worst_key_is_height_bandwidth_and_position() -> None:
    assert worst_key((3, variant(1500, (1280, 720)))) == (720, 1500, 3)
    assert (
        min([(0, variant(900, (1280, 720))), (1, variant(800, (1280, 720)))], key=worst_key)[0] == 1
    )


def test_a_stream_is_described_by_size_and_rate() -> None:
    assert describe(variant(800_000, (1280, 720))) == "720p, 800 kbps"
    assert describe(variant(64_000)) == "unknown size, 64 kbps"


def test_a_stream_is_described_in_full_for_a_failed_choice() -> None:
    assert describe_full(variant(2_000_000, (1280, 720), name="HD")) == (
        "1280x720, 2000000 bit/s, name 'HD'"
    )
    assert describe_full(variant(64_000)) == "audio only, 64000 bit/s"


def ladder() -> list[tuple[int, Variant]]:
    sizes = [(640, 360), (1280, 720), (1920, 1080)]
    return [
        (index, variant(1000 * (index + 1), size, uri=f"{size[1]}.m3u8"))
        for index, size in enumerate(sizes)
    ]


def test_the_closest_stream_is_the_best_one_at_or_below_the_target() -> None:
    notes: list[str] = []
    assert closest_to(ladder(), 800, notes).uri == "720.m3u8"
    assert closest_to(ladder(), 720, notes).uri == "720.m3u8"
    assert closest_to(ladder(), 5000, notes).uri == "1080.m3u8"
    assert notes == []


def test_when_every_stream_is_larger_the_smallest_is_chosen_and_the_note_says_so() -> None:
    notes: list[str] = []
    assert closest_to(ladder(), 240, notes).uri == "360.m3u8"
    assert len(notes) == 1
    assert "240p" in notes[0]
    assert "360p" in notes[0]
