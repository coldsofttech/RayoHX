"""Network settings: headers, timeouts, retries, TLS, proxy and rate limit."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rayohx._redaction import REDACTED, redact_headers
from rayohx.config._common import check_positive, frozen_map
from rayohx.errors import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path
    from typing import Any

    from rayohx.config.proxy import ProxyConfig

DEFAULT_USER_AGENT = "RayoHX"

_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


@dataclass(frozen=True, slots=True, kw_only=True)
class NetworkConfig:
    """How requests are made."""

    headers: Mapping[str, str] = field(default_factory=dict, repr=False)
    cookies: Mapping[str, str] = field(default_factory=dict, repr=False)
    user_agent: str = DEFAULT_USER_AGENT
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    total_timeout: float | None = None
    retries: int = 3
    backoff_factor: float = 0.5
    max_redirects: int = 10
    #: ``True`` verifies with the default trust store, ``False`` turns verification off, and a
    #: path verifies against that CA bundle.
    verify_tls: bool | Path = True
    proxy: ProxyConfig | None = None
    #: Cap on download speed in bytes per second across all workers; ``None`` means no cap.
    rate_limit: int | None = None

    def __post_init__(self) -> None:
        for name, value in self.headers.items():
            if not _HEADER_NAME.match(name):
                raise ConfigurationError(f"{name!r} is not a valid header name.")
            if any(char in value for char in "\r\n\0"):
                raise ConfigurationError(f"The value of header {name!r} contains a line break.")
        for name, value in self.cookies.items():
            if not name or any(char in name + value for char in "\r\n\0;"):
                raise ConfigurationError(f"The cookie {name!r} is not valid.")
        if not self.user_agent.strip() or any(char in self.user_agent for char in "\r\n\0"):
            raise ConfigurationError("The user agent must be a single non-empty line.")
        check_positive("connect_timeout", self.connect_timeout)
        check_positive("read_timeout", self.read_timeout)
        check_positive("total_timeout", self.total_timeout, allow_none=True)
        check_positive("rate_limit", self.rate_limit, allow_none=True)
        if self.retries < 0:
            raise ConfigurationError("retries must not be negative.")
        if self.backoff_factor < 0:
            raise ConfigurationError("backoff_factor must not be negative.")
        if self.max_redirects < 0:
            raise ConfigurationError("max_redirects must not be negative.")
        object.__setattr__(self, "headers", frozen_map(self.headers))
        object.__setattr__(self, "cookies", frozen_map(self.cookies))

    def request_headers(self) -> dict[str, str]:
        """The headers to send: the user agent, then the user's own, which win on a clash."""
        merged = {"User-Agent": self.user_agent}
        for name, value in self.headers.items():
            for existing in [key for key in merged if key.lower() == name.lower()]:
                del merged[existing]
            merged[name] = value
        return merged

    def as_dict(self) -> dict[str, Any]:
        """A serializable view without secrets."""
        from pathlib import Path

        verify = str(self.verify_tls) if isinstance(self.verify_tls, Path) else self.verify_tls
        return {
            "headers": redact_headers(self.headers),
            "cookies": dict.fromkeys(self.cookies, REDACTED),
            "user_agent": self.user_agent,
            "connect_timeout": self.connect_timeout,
            "read_timeout": self.read_timeout,
            "total_timeout": self.total_timeout,
            "retries": self.retries,
            "backoff_factor": self.backoff_factor,
            "max_redirects": self.max_redirects,
            "verify_tls": verify,
            "proxy": self.proxy.as_dict() if self.proxy else None,
            "rate_limit": self.rate_limit,
        }
