"""One ``EXT-X-STREAM-INF`` entry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rayohx.models.playlist.resolution import Resolution


@dataclass(frozen=True, slots=True, kw_only=True)
class Variant:
    """One ``EXT-X-STREAM-INF`` entry: a rendition of the video."""

    uri: str
    bandwidth: int
    average_bandwidth: int | None = None
    resolution: Resolution | None = None
    codecs: tuple[str, ...] = ()
    frame_rate: float | None = None
    video_range: str | None = None
    video_group: str | None = None
    audio_group: str | None = None
    subtitle_group: str | None = None
    name: str | None = None

    def __post_init__(self) -> None:
        if self.bandwidth < 0:
            raise ValueError("bandwidth must not be negative")
        object.__setattr__(self, "codecs", tuple(self.codecs))

    @property
    def height(self) -> int | None:
        """Picture height in pixels, when known."""
        return self.resolution.height if self.resolution else None
