"""A downloaded segment."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class SegmentData:
    """A downloaded segment, decrypted. ``init`` is the initialization section to write first."""

    index: int
    media: bytes
    init: bytes = b""

    @property
    def size(self) -> int:
        """Bytes this segment adds to the output."""
        return len(self.init) + len(self.media)
