"""Writing and reading sizes such as ``20G`` and ``1.5 MiB``."""

from __future__ import annotations

import re

from rayohx.errors import ConfigurationError

_UNITS = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
_SIZE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kmgt]?)(?:i?b)?\s*$", re.IGNORECASE)


def parse_size(text: str | int, *, what: str = "size") -> int:
    """Bytes from ``20G``, ``512 MiB``, ``1.5g`` or a plain number. Units are powers of 1024."""
    if isinstance(text, int):
        if text < 0:
            raise ConfigurationError(f"The {what} must not be negative.")
        return text
    match = _SIZE.match(text)
    if not match:
        raise ConfigurationError(
            f"The {what} {text!r} is not a size.", hint="Write it like 20G, 512M or 1.5G."
        )
    return int(float(match.group(1)) * _UNITS[match.group(2).lower()])


def format_size(count: int | float) -> str:
    """A short size such as ``1.5 GiB``."""
    value = float(count)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(value) < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError  # pragma: no cover
