"""Proxy settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from rayohx._redaction import REDACTED, redact_url
from rayohx.errors import ConfigurationError

if TYPE_CHECKING:
    from typing import Any

#: Proxy schemes accepted today. SOCKS can be added here without touching the callers.
SUPPORTED_PROXY_SCHEMES = frozenset({"http", "https"})


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ProxyConfig:
    """An HTTP or HTTPS proxy. Credentials go in ``username`` and ``password``, or in the URL."""

    url: str
    username: str | None = None
    password: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        cleaned = self.url.strip()
        try:
            parts = urlsplit(cleaned)
            hostname = parts.hostname
        except ValueError as exc:
            raise ConfigurationError("The proxy address is not valid.") from exc
        if parts.scheme.lower() not in SUPPORTED_PROXY_SCHEMES or not hostname:
            raise ConfigurationError(
                "The proxy address must look like http://host:port or https://host:port.",
                hint="SOCKS proxies are not supported yet.",
            )
        if (self.username is None) != (self.password is None):
            raise ConfigurationError("Set both the proxy username and password, or neither.")
        object.__setattr__(self, "url", cleaned)

    def __repr__(self) -> str:
        return f"ProxyConfig(url={self.redacted_url!r})"

    @property
    def redacted_url(self) -> str:
        """The proxy address with any credentials hidden."""
        return redact_url(self.url)

    def as_dict(self) -> dict[str, Any]:
        """A serializable view without secrets."""
        return {
            "url": self.redacted_url,
            "username": REDACTED if self.username else None,
            "password": REDACTED if self.password else None,
        }
