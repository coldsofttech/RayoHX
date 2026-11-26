import pytest
from rayohx_pytest.media import box, fmp4_fragment, fmp4_init, ts_payload

from rayohx import ContainerFormat
from rayohx._download._containers import (
    sniff_container,
)

TS = ContainerFormat.MPEG_TS


MP4 = ContainerFormat.FMP4


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (ts_payload(1, 3), TS),
        (ts_payload(1, 1), TS),
        (fmp4_init(), MP4),
        (fmp4_fragment(1), MP4),
        (box(b"styp", b"msdh"), MP4),
        (b"WEBVTT\n\n00:00.000 --> 00:01.000\nHi", ContainerFormat.WEBVTT),
        (b"\xef\xbb\xbfWEBVTT\n", ContainerFormat.WEBVTT),
        (b"<html>denied</html>", ContainerFormat.UNKNOWN),
        (b"", ContainerFormat.UNKNOWN),
        (b"\x47" + bytes(300), ContainerFormat.UNKNOWN),  # sync byte alone, packets do not line up
        (bytes(100), ContainerFormat.UNKNOWN),
    ],
)
def test_sniffing(data: bytes, expected: ContainerFormat) -> None:
    assert sniff_container(data) is expected
