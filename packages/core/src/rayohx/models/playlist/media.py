"""A playlist of segments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rayohx.enums import ContainerFormat

if TYPE_CHECKING:
    from rayohx.models.segment import Segment


@dataclass(frozen=True, slots=True, kw_only=True)
class MediaPlaylist:
    """A playlist of segments."""

    uri: str
    segments: tuple[Segment, ...]
    target_duration: float
    media_sequence: int = 0
    end_list: bool = False
    version: int | None = None
    playlist_type: str | None = None
    container: ContainerFormat = ContainerFormat.UNKNOWN

    def __post_init__(self) -> None:
        object.__setattr__(self, "segments", tuple(self.segments))
        if self.target_duration < 0:
            raise ValueError("target_duration must not be negative")

    @property
    def segment_count(self) -> int:
        """Number of segments."""
        return len(self.segments)

    @property
    def total_duration(self) -> float:
        """Sum of the segment durations, in seconds."""
        return sum(segment.duration for segment in self.segments)

    @property
    def is_vod(self) -> bool:
        """Whether the playlist is complete and will not grow."""
        return self.end_list or self.playlist_type == "VOD"
