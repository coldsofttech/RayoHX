"""One media segment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from rayohx.models.encryption_info import EncryptionInfo
    from rayohx.models.init_map import InitMap
    from rayohx.models.segment_range import SegmentRange


@dataclass(frozen=True, slots=True, kw_only=True)
class Segment:
    """One media segment, with everything needed to fetch and place it."""

    index: int
    uri: str
    duration: float
    sequence_number: int
    byte_range: SegmentRange | None = None
    init_map: InitMap | None = None
    encryption: EncryptionInfo | None = None
    discontinuity: bool = False
    program_date_time: datetime | None = None
    title: str = ""

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("index must not be negative")
        if self.duration < 0:
            raise ValueError("duration must not be negative")
