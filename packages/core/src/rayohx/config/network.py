"""Network settings: headers, timeouts, retries, TLS, proxy and rate limit."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path
    from typing import Any

    from rayohx.config.proxy import ProxyConfig

DEFAULT_USER_AGENT = "RayoHX"

_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_HOSTNAME = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)*$"
)


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
    #: Read proxies from ``HTTP_PROXY``, ``HTTPS_PROXY``, ``ALL_PROXY`` and ``NO_PROXY`` (any
    #: letter case) when ``proxy`` is not set. Off by default so nothing changes silently.
    proxy_from_env: bool = False
    #: A client certificate (PEM) for servers that require mutual TLS, and its private key if
    #: that is in a separate file.
    client_cert: Path | None = None
    client_key: Path | None = None
    client_key_password: str | None = field(default=None, repr=False)
    #: Cap on download speed in bytes per second across all workers; ``None`` means no cap.
    rate_limit: int | None = None
    #: Hosts, besides the one the download starts from, that may receive credentials
    #: (``Authorization``, ``Cookie`` and other secret headers). Other hosts get none of them.
    credential_hosts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        from rayohx.config._common import check_positive, frozen_map
        from rayohx.errors import ConfigurationError

        for host in self.credential_hosts:
            if not _HOSTNAME.match(host):
                raise ConfigurationError(
                    f"{host!r} is not a valid host name.",
                    hint="Give a bare host such as cdn.example.com, without scheme or path.",
                )
        object.__setattr__(
            self, "credential_hosts", tuple(host.lower() for host in self.credential_hosts)
        )
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
        if self.client_cert is None and (self.client_key or self.client_key_password):
            raise ConfigurationError(
                "A client key was given without a client certificate.",
                hint="Set client_cert (--client-cert) as well.",
            )
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

        from rayohx._redaction import REDACTED, redact_headers

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
            "proxy_from_env": self.proxy_from_env,
            "client_cert": str(self.client_cert) if self.client_cert else None,
            "client_key": str(self.client_key) if self.client_key else None,
            "client_key_password": REDACTED if self.client_key_password else None,
            "rate_limit": self.rate_limit,
            "credential_hosts": list(self.credential_hosts),
        }
