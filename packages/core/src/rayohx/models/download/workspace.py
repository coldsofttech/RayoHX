"""A leftover working folder an interrupted download left behind."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class LeftoverWorkspace:
    """One leftover working folder."""

    path: Path
    size: int
    """Bytes on disk."""
    age_days: float
    """Days since it was last used."""
    in_use: bool
    """Whether a running download holds it."""
