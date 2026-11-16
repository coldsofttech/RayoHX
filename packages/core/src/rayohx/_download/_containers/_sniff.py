"""Guessing a segment's format from its first bytes."""

from rayohx._download._containers._formats import (
    FMP4_INIT_START,
    FMP4_SEGMENT_START,
    looks_like_ts,
)
from rayohx.enums import ContainerFormat


def sniff_container(data: bytes) -> ContainerFormat:
    """Guess the format from the first bytes of a segment (or of an initialization section)."""
    if data.lstrip(b"\xef\xbb\xbf").startswith(b"WEBVTT"):
        return ContainerFormat.WEBVTT
    if looks_like_ts(data):
        return ContainerFormat.MPEG_TS
    if len(data) >= 8 and data[4:8] in (FMP4_SEGMENT_START | FMP4_INIT_START):
        return ContainerFormat.FMP4
    return ContainerFormat.UNKNOWN
