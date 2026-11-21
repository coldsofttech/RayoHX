import pytest

from rayohx._download._containers._formats import (
    FMP4_INIT_START,
    FMP4_SEGMENT_START,
    TS_PACKET,
    TS_SYNC,
    looks_like_ts,
)


def packets(count: int, *, broken: int | None = None) -> bytes:
    """``count`` TS packets; the one at index ``broken`` lacks its sync byte."""
    return b"".join(
        bytes([0x00 if index == broken else TS_SYNC]) + bytes(TS_PACKET - 1)
        for index in range(count)
    )


def test_a_ts_packet_is_188_bytes_starting_with_the_sync_byte() -> None:
    assert TS_PACKET == 188
    assert TS_SYNC == 0x47


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"", False),
        (bytes(TS_PACKET), False),  # no sync byte
        (packets(1), True),  # one packet is accepted: there is nothing to line up yet
        (packets(2), True),
        (packets(3), True),
        (packets(2, broken=1), False),  # the second sync byte is missing
        (packets(3, broken=2), False),  # the third sync byte is missing
        (packets(4, broken=3), True),  # only the first three packets are checked
        (bytes([TS_SYNC]) + bytes(300), False),  # a sync byte alone, packets do not line up
    ],
)
def test_telling_transport_stream_data_by_its_sync_bytes(data: bytes, expected: bool) -> None:
    assert looks_like_ts(data) is expected


def test_the_start_boxes_of_the_two_kinds_of_mp4_data_differ() -> None:
    assert b"ftyp" in FMP4_INIT_START
    assert b"moov" in FMP4_INIT_START
    assert b"moof" in FMP4_SEGMENT_START
    assert b"moof" not in FMP4_INIT_START
    assert b"ftyp" not in FMP4_SEGMENT_START
    assert b"styp" in FMP4_INIT_START & FMP4_SEGMENT_START
