"""A byte range inside a resource."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Self

_BYTE_RANGE = re.compile(r"^(\d+)(?:@(\d+))?$")


@dataclass(frozen=True, slots=True)
class SegmentRange:
    """A byte range inside a resource. ``offset`` is ``None`` when it follows the previous one."""

    length: int
    offset: int | None = None

    def __post_init__(self) -> None:
        if self.length <= 0:
            raise ValueError("length must be positive")
        if self.offset is not None and self.offset < 0:
            raise ValueError("offset must not be negative")

    @classmethod
    def parse(cls, text: str) -> Self:
        """Read the ``length[@offset]`` form used by ``EXT-X-BYTERANGE`` and ``EXT-X-MAP``.

        Raises:
            InvalidPlaylistError: If ``text`` is not in that form.
        """
        match = _BYTE_RANGE.match(text.strip())
        if not match or int(match.group(1)) == 0:
            from rayohx.errors import InvalidPlaylistError

            raise InvalidPlaylistError(f"{text!r} is not a valid byte range.")
        offset = int(match.group(2)) if match.group(2) is not None else None
        return cls(int(match.group(1)), offset)

    def http_header(self) -> str:
        """The ``Range`` header value for this range.

        Raises:
            ValueError: If the offset is not known yet.
        """
        if self.offset is None:
            raise ValueError("the offset must be resolved before building a Range header")
        return f"bytes={self.offset}-{self.offset + self.length - 1}"
