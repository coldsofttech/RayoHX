"""An audio rendition."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class AudioTrack:
    """An audio rendition. ``uri`` is ``None`` when the audio is inside the video segments."""

    group_id: str
    name: str
    language: str | None = None
    uri: str | None = None
    default: bool = False
    autoselect: bool = False
    forced: bool = False
    channels: str | None = None
    characteristics: tuple[str, ...] = ()
