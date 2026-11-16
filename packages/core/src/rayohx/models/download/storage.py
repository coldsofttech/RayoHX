"""How much data a download has moved and kept."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class StorageMetrics:
    """A snapshot of how much data the download has moved and kept, in bytes."""

    output_bytes: int = 0
    temporary_bytes: int = 0
    working_bytes: int = 0
    peak_temporary_bytes: int = 0
    downloaded_bytes: int = 0
    written_bytes: int = 0
