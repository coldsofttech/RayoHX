"""An ``EXT-X-MAP`` initialization section."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rayohx.models.segment_range import SegmentRange


@dataclass(frozen=True, slots=True)
class InitMap:
    """An ``EXT-X-MAP`` initialization section."""

    uri: str
    byte_range: SegmentRange | None = None
