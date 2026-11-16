"""How a download ended."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rayohx._redaction import redact_url
from rayohx.enums import DownloadState

if TYPE_CHECKING:
    from rayohx.models.download.output import OutputInfo
    from rayohx.models.download.progress import DownloadProgress


@dataclass(frozen=True, slots=True, kw_only=True)
class DownloadResult:
    """How a download ended. A cancelled download has its own state, not a failure."""

    download_id: str
    url: str
    state: DownloadState
    elapsed_seconds: float
    progress: DownloadProgress
    output: OutputInfo | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.state.is_terminal:
            raise ValueError("a result needs a finished state")
        object.__setattr__(self, "url", redact_url(self.url))

    @property
    def success(self) -> bool:
        """Whether the download completed."""
        return self.state is DownloadState.COMPLETED

    @property
    def cancelled(self) -> bool:
        """Whether the download was cancelled."""
        return self.state is DownloadState.CANCELLED
