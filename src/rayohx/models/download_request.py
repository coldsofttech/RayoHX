"""A web address to download and the settings to download it with."""

from __future__ import annotations

from dataclasses import dataclass, field

from rayohx._redaction import redact_url
from rayohx.config.download import DownloadConfig
from rayohx.config.url import validate_url


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DownloadRequest:
    """A web address to download and the settings to download it with."""

    url: str
    config: DownloadConfig = field(default_factory=DownloadConfig)

    def __post_init__(self) -> None:
        object.__setattr__(self, "url", validate_url(self.url))

    def __repr__(self) -> str:
        return f"DownloadRequest(url={self.redacted_url!r}, config={self.config!r})"

    @property
    def redacted_url(self) -> str:
        """The address with credentials hidden, for logs and messages."""
        return redact_url(self.url)
