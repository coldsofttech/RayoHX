"""Picture size."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rayohx.errors import InvalidPlaylistError

if TYPE_CHECKING:
    from typing import Self

_RESOLUTION = re.compile(r"^(\d+)x(\d+)$")


@dataclass(frozen=True, slots=True, order=True)
class Resolution:
    """Width and height in pixels."""

    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")

    @classmethod
    def parse(cls, text: str) -> Self:
        """Read ``1920x1080``.

        Raises:
            InvalidPlaylistError: If ``text`` is not in that form.
        """
        match = _RESOLUTION.match(text.strip())
        if not match or int(match.group(1)) == 0 or int(match.group(2)) == 0:
            raise InvalidPlaylistError(f"{text!r} is not a valid resolution.")
        return cls(int(match.group(1)), int(match.group(2)))

    @property
    def pixels(self) -> int:
        """Total pixel count."""
        return self.width * self.height

    def __str__(self) -> str:
        return f"{self.width}x{self.height}"
