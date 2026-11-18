"""Limits and helpers shared by the HTTP client and the response checks."""

import os
import ssl
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

from rayohx._redaction import redact_url
from rayohx.config import ProxyConfig
from rayohx.errors import (
    ConfigurationError,
    InvalidResponseError,
    NetworkConnectionError,
    NetworkError,
    NetworkTimeoutError,
    TLSError,
)

CHUNK_SIZE = 64 * 1024
MAX_PLAYLIST_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_BYTES = 512 * 1024 * 1024
MAX_RETRY_AFTER = 60.0
DEFAULT_POOL_SIZE = 16


def host_of(url: str) -> str:
    """The lower-cased host name of ``url``, or an empty string."""
    return (urlsplit(url).hostname or "").lower()


def verify(value: bool | Path) -> bool | ssl.SSLContext:
    """The ``httpx`` TLS setting for a ``verify_tls`` value: a flag or a CA bundle path."""
    if isinstance(value, Path):
        try:
            return ssl.create_default_context(cafile=str(value))
        except (OSError, ssl.SSLError) as exc:
            raise ConfigurationError(
                f"The certificate file {value} cannot be read.",
                hint="Give a PEM file of trusted certificate authorities.",
            ) from exc
    return value


def tls_context(
    value: bool | Path,
    cert: Path | None = None,
    key: Path | None = None,
    password: str | None = None,
) -> bool | ssl.SSLContext:
    """The ``httpx`` TLS setting, with a client certificate loaded when one is given."""
    base = verify(value)
    if cert is None:
        return base
    if isinstance(base, ssl.SSLContext):
        context = base
    else:
        context = ssl.create_default_context()
        if base is False:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
    try:
        context.load_cert_chain(
            certfile=str(cert), keyfile=str(key) if key else None, password=password
        )
    except (OSError, ssl.SSLError, ValueError) as exc:
        raise ConfigurationError(
            f"The client certificate {cert} cannot be used.",
            hint="Give a PEM certificate, and its key file if the key is separate. "
            "Check the key password.",
        ) from exc
    return context


def environment_proxies(
    env: Mapping[str, str] | None = None,
) -> tuple[dict[str, ProxyConfig], tuple[str, ...]]:
    """Proxies from the environment, by scheme (``http``, ``https``, ``all``), and ``NO_PROXY``.

    Names are matched in lower case first, then upper case, as most tools do. A value that is
    not a usable proxy address is ignored, so a stray variable never breaks a download.
    """
    source = os.environ if env is None else env

    def lookup(name: str) -> str:
        return (source.get(name.lower()) or source.get(name.upper()) or "").strip()

    found: dict[str, ProxyConfig] = {}
    for scheme, name in (("http", "http_proxy"), ("https", "https_proxy"), ("all", "all_proxy")):
        value = lookup(name)
        if not value:
            continue
        if "://" not in value:
            value = f"http://{value}"
        try:
            found[scheme] = ProxyConfig(url=value)
        except ConfigurationError:
            continue
    skip = tuple(part.strip().lower() for part in lookup("no_proxy").split(",") if part.strip())
    return found, skip


def proxy_url(proxy: ProxyConfig) -> str:
    """The proxy address with its credentials, if any, percent-encoded into it."""
    if proxy.username is None:
        return proxy.url
    parts = urlsplit(proxy.url)
    netloc_host = parts.netloc.rpartition("@")[2]
    user = quote(proxy.username, safe="")
    password = quote(proxy.password or "", safe="")
    return f"{parts.scheme}://{user}:{password}@{netloc_host}{parts.path}"


def translate(exc: Exception, url: str) -> NetworkError:
    """Turn an ``httpx`` failure into the matching RayoHX error."""
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
