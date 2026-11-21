"""Limits and helpers shared by the HTTP client and the response checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import ssl
    from pathlib import Path

    from rayohx.config import ProxyConfig
    from rayohx.errors import NetworkError

CHUNK_SIZE = 64 * 1024
MAX_PLAYLIST_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_BYTES = 512 * 1024 * 1024
MAX_RETRY_AFTER = 60.0
DEFAULT_POOL_SIZE = 16


def host_of(url: str) -> str:
    """The lower-cased host name of ``url``, or an empty string."""
    from urllib.parse import urlsplit

    return (urlsplit(url).hostname or "").lower()


def verify(value: bool | Path) -> bool | ssl.SSLContext:
    """The ``httpx`` TLS setting for a ``verify_tls`` value: a flag or a CA bundle path."""
    import ssl
    from pathlib import Path

    from rayohx.errors import ConfigurationError

    if isinstance(value, Path):
        try:
            return ssl.create_default_context(cafile=str(value))
        except (OSError, ssl.SSLError) as exc:
            raise ConfigurationError(
                f"The certificate file {value} cannot be read.",
                hint="Give a PEM file of trusted certificate authorities.",
            ) from exc
    return value


def proxy_url(proxy: ProxyConfig) -> str:
    """The proxy address with its credentials, if any, percent-encoded into it."""
    from urllib.parse import quote, urlsplit

    if proxy.username is None:
        return proxy.url
    parts = urlsplit(proxy.url)
    netloc_host = parts.netloc.rpartition("@")[2]
    user = quote(proxy.username, safe="")
    password = quote(proxy.password or "", safe="")
    return f"{parts.scheme}://{user}:{password}@{netloc_host}{parts.path}"


def translate(exc: Exception, url: str) -> NetworkError:
    """Turn an ``httpx`` failure into the matching RayoHX error."""
    import ssl

    import httpx

    from rayohx._redaction import redact_url
    from rayohx.errors import (
        InvalidResponseError,
        NetworkConnectionError,
        NetworkError,
        NetworkTimeoutError,
        TLSError,
    )

    shown = redact_url(url)
    cause: BaseException | None = exc
    while cause is not None:
        if isinstance(cause, ssl.SSLError):
            return TLSError(
                f"The secure connection to {shown} failed the certificate check.",
                hint="If you trust this server, supply its certificate authority file or turn "
                "TLS verification off.",
            )
        cause = cause.__cause__ or cause.__context__
    if isinstance(exc, httpx.TimeoutException):
        return NetworkTimeoutError(
            f"The server did not answer in time: {shown}",
            hint="Try a longer timeout, fewer parallel downloads, or check the connection.",
        )
    if isinstance(exc, httpx.ProxyError):
        return NetworkConnectionError(
            f"The proxy refused or could not forward the request to {shown}",
            hint="Check the proxy address and its username and password.",
        )
    if isinstance(exc, httpx.DecodingError):
        return InvalidResponseError(f"The response from {shown} could not be decoded.")
    if isinstance(exc, httpx.UnsupportedProtocol | httpx.InvalidURL):
        return NetworkError(f"The address cannot be requested: {shown}")
    if isinstance(exc, httpx.TransportError):
        return NetworkConnectionError(
            f"The connection to {shown} failed.",
            hint="Check the connection, the address and any proxy.",
        )
    return NetworkError(f"The request to {shown} failed.")
