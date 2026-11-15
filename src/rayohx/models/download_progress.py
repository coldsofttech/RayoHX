"""A snapshot of a download."""

from __future__ import annotations

from dataclasses import dataclass, field

from rayohx.enums import DownloadState
from rayohx.models.storage_metrics import StorageMetrics


@dataclass(frozen=True, slots=True, kw_only=True)
class DownloadProgress:
    """A snapshot of a download, ready to show in any front end."""

    state: DownloadState = DownloadState.QUEUED
    downloaded_bytes: int = 0
    written_bytes: int = 0
    total_bytes: int | None = None
    completed_segments: int = 0
    total_segments: int = 0
    speed: float = 0.0
    average_speed: float = 0.0
    eta_seconds: float | None = None
    active_workers: int = 0
    storage: StorageMetrics = field(default_factory=StorageMetrics)

    @property
    def fraction(self) -> float | None:
        """Share done between 0 and 1, from bytes when the total is known, else from segments."""
        if self.total_bytes:
            return min(1.0, self.downloaded_bytes / self.total_bytes)
        if self.total_segments:
            return min(1.0, self.completed_segments / self.total_segments)
        return None
