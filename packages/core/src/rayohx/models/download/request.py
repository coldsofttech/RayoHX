"""A web address to download and the settings to download it with."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rayohx.config.download import DownloadConfig


def _config() -> DownloadConfig:
    from rayohx.config.download import DownloadConfig

    return DownloadConfig()


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DownloadRequest:
    """A web address to download and the settings to download it with."""

    url: str
    config: DownloadConfig = field(default_factory=_config)

    def __post_init__(self) -> None:
        from rayohx.config.url import validate_url

        object.__setattr__(self, "url", validate_url(self.url))

    def __repr__(self) -> str:
        return f"DownloadRequest(url={self.redacted_url!r}, config={self.config!r})"

    @property
    def redacted_url(self) -> str:
        """The address with credentials hidden, for logs and messages."""
        from rayohx._redaction import redact_url

        return redact_url(self.url)
