"""File names a caller may ask for. They can never leave the download folder."""

from __future__ import annotations

import re

from rayohx.errors import ConfigurationError

_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RESERVED = frozenset({".", ".."})


def safe_filename(name: str) -> str:
    """Return ``name`` stripped, or raise if it could point outside the download folder."""
    cleaned = name.strip()
    if not cleaned or cleaned in _RESERVED or _BAD.search(cleaned) or len(cleaned) > 200:
        raise ConfigurationError(
            "Use a plain file name without folders or special characters.",
            hint="For example: movie.mp4",
        )
    return cleaned
