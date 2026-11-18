"""Checking one downloaded segment against the format the playlist promised."""

from rayohx._download._containers._formats import (
    FMP4_INIT_START,
    FMP4_SEGMENT_START,
    TS_PACKET,
    looks_like_ts,
)
from rayohx.enums import ContainerFormat


def check_segment(
    container: ContainerFormat, data: bytes, *, is_init: bool = False, strict: bool = False
) -> str | None:
    """Return what is wrong with a downloaded segment, or ``None`` if it looks right.

    ``strict`` also looks for data that was cut off: a transport stream whose length is not a
    whole number of packets, or an MP4 whose boxes do not add up to the length received.
    """
    if container is ContainerFormat.MPEG_TS:
        if not looks_like_ts(data):
            return "it is not MPEG-TS data"
        if strict and len(data) % TS_PACKET:
            return f"it ends in the middle of a packet ({len(data) % TS_PACKET} extra bytes)"
    elif container is ContainerFormat.FMP4:
        allowed = FMP4_INIT_START if is_init else FMP4_SEGMENT_START
        if len(data) < 8 or data[4:8] not in allowed:
            return "it is not fragmented MP4 data"
        if strict and not _boxes_fit(data):
            return "its MP4 boxes do not add up to the data received (it looks cut off)"
    return None


def _boxes_fit(data: bytes) -> bool:
    """Whether the top-level boxes exactly fill ``data``."""
    position = 0
    while position < len(data):
        if len(data) - position < 8:
            return False
        length = int.from_bytes(data[position : position + 4], "big")
        if length == 1:
            if len(data) - position < 16:
                return False
            length = int.from_bytes(data[position + 8 : position + 16], "big")
        elif length == 0:
            return True  # a box that runs to the end of the data
        if length < 8:
            return False
        position += length
    return position == len(data)
