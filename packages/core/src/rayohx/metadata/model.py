"""What a stream tells us about the media in it."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True, slots=True)
class Chapter:
    """A named point in the media."""

    start: float
    title: str
    end: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "title": self.title}


@dataclass(frozen=True, slots=True, kw_only=True)
class MetadataInfo:
    """Information about the media, from the playlists and the settings."""

    title: str | None = None
    description: str | None = None
    #: A language code such as ``en``.
    language: str | None = None
    #: How long the media is, in seconds.
    duration: float | None = None
    #: Where the cover picture is.
    artwork_url: str | None = None
    chapters: tuple[Chapter, ...] = ()
    #: When the media starts, if the stream says (``EXT-X-PROGRAM-DATE-TIME``).
    start_time: datetime | None = None
    #: The address it came from, with any secrets removed.
    source: str | None = None
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not any(
            (self.title, self.description, self.language, self.artwork_url, self.chapters)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "language": self.language,
            "duration": self.duration,
            "artwork_url": self.artwork_url,
            "chapters": [c.to_dict() for c in self.chapters],
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "source": self.source,
            "extra": dict(self.extra),
        }
