"""Which hosts may receive secrets, and the headers each request carries."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rayohx.config import NetworkConfig
    from rayohx.models import SegmentRange


class CredentialScope:
    """Decides where secret headers and cookies may go, and builds each request's headers.

    Secrets go to the host the download started from and to ``credential_hosts``. When no origin
    is given, the host of the first request becomes the origin. Safe to share between threads.
    """

    def __init__(self, config: NetworkConfig, origin_url: str | None = None) -> None:
        import threading

        from rayohx._http._common import host_of

        self._config = config
        self._lock = threading.Lock()
        self._trusted = set(config.credential_hosts)
        self._adopt_first_host = origin_url is None
        if origin_url is not None:
            self._trusted.add(host_of(origin_url))

    def is_trusted(self, host: str) -> bool:
        """Whether ``host`` may receive secrets."""
        with self._lock:
            if self._adopt_first_host:
                self._trusted.add(host)
                self._adopt_first_host = False
            return host in self._trusted

    def headers_for(
        self, url: str, accept_encoding: str, byte_range: SegmentRange | None
    ) -> dict[str, str]:
        """The headers to send to ``url``, with secrets left out for hosts that are not trusted."""
        from rayohx._http._common import host_of
        from rayohx._redaction import is_sensitive_name

        trusted = self.is_trusted(host_of(url))
        headers = {"Accept-Encoding": accept_encoding}
        for name, value in self._config.request_headers().items():
            if is_sensitive_name(name) and not trusted:
                continue
            for existing in [key for key in headers if key.lower() == name.lower()]:
                del headers[existing]
            headers[name] = value
        has_cookie_header = any(name.lower() == "cookie" for name in headers)
        if trusted and self._config.cookies and not has_cookie_header:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self._config.cookies.items())
        if byte_range is not None:
            headers["Range"] = byte_range.http_header()
        return headers
