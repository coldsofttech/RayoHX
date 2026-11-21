"""Checking one downloaded segment against the format the playlist promised."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rayohx.enums import ContainerFormat


def check_segment(container: ContainerFormat, data: bytes, *, is_init: bool = False) -> str | None:
    """Return what is wrong with a downloaded segment, or ``None`` if it looks right."""
    from rayohx._download._containers._formats import (
        FMP4_INIT_START,
        FMP4_SEGMENT_START,
        looks_like_ts,
    )
    from rayohx.enums import ContainerFormat

    if container is ContainerFormat.MPEG_TS:
        if not looks_like_ts(data):
            return "it is not MPEG-TS data"
    elif container is ContainerFormat.FMP4:
        allowed = FMP4_INIT_START if is_init else FMP4_SEGMENT_START
        if len(data) < 8 or data[4:8] not in allowed:
            return "it is not fragmented MP4 data"
    return None
