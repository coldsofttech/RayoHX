import pytest
from rayohx_testing.media import ts_payload

from rayohx import ContainerFormat
from rayohx._download._containers import (
    check_segment,
)
from tests.helpers.media import box, fmp4_fragment, fmp4_init

TS = ContainerFormat.MPEG_TS


MP4 = ContainerFormat.FMP4


@pytest.mark.parametrize(
    ("container", "data", "ok"),
    [
        (TS, ts_payload(0), True),
        (TS, b"<html>", False),
        (TS, b"", False),
        (MP4, fmp4_fragment(0), True),
        (MP4, b"<html>denied</html>", False),
        (MP4, b"abc", False),
        (ContainerFormat.UNKNOWN, b"anything", True),
        (ContainerFormat.WEBVTT, b"anything", True),
    ],
)
def test_segments_are_checked_against_their_format(
    container: ContainerFormat, data: bytes, ok: bool
) -> None:
    assert (check_segment(container, data) is None) is ok


def test_an_init_section_may_start_with_ftyp_or_moov() -> None:
    assert check_segment(MP4, fmp4_init(), is_init=True) is None
    assert check_segment(MP4, box(b"moov"), is_init=True) is None
    assert check_segment(MP4, fmp4_fragment(0), is_init=True) is not None
    assert check_segment(MP4, box(b"ftyp"), is_init=False) is not None
