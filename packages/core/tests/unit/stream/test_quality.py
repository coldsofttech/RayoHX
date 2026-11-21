import pytest

from rayohx import Resolution, Variant
from rayohx.stream.quality import quality_height


def with_size(size: tuple[int, int] | None) -> Variant:
    return Variant(uri="v.m3u8", bandwidth=1, resolution=Resolution(*size) if size else None)


def test_a_stream_without_a_size_has_no_quality() -> None:
    assert quality_height(with_size(None)) == 0


@pytest.mark.parametrize(
    ("size", "height"),
    [
        ((640, 360), 360),
        ((1280, 720), 720),
        ((1920, 1080), 1080),
        ((3840, 2160), 2160),
        ((1920, 800), 800),  # a wide film: the shorter side, not a standard height
    ],
)
def test_landscape_video_is_judged_by_its_height(size: tuple[int, int], height: int) -> None:
    assert quality_height(with_size(size)) == height


@pytest.mark.parametrize(("size", "height"), [((720, 1280), 720), ((1080, 1920), 1080)])
def test_portrait_video_is_judged_by_its_width(size: tuple[int, int], height: int) -> None:
    assert quality_height(with_size(size)) == height


def test_square_video_is_judged_by_either_side() -> None:
    assert quality_height(with_size((1080, 1080))) == 1080
