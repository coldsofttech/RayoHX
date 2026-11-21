"""A subtitle rendition."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class SubtitleTrack:
    """A subtitle rendition."""

    group_id: str
    name: str
    language: str | None = None
    uri: str | None = None
    default: bool = False
    autoselect: bool = False
    forced: bool = False
    characteristics: tuple[str, ...] = ()
