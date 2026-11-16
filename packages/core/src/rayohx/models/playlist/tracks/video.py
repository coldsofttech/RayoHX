"""An alternative video rendition."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class VideoTrack:
    """An alternative video rendition (``EXT-X-MEDIA`` of type ``VIDEO``)."""

    group_id: str
    name: str
    uri: str | None = None
    default: bool = False
    autoselect: bool = False
