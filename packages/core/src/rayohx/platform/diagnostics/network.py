"""Finding out where a connection fails: name lookup, connecting, the secure handshake, the answer.

``probe_network`` makes the same steps a download makes, one at a time, times each, and says which
one failed. It is careful with what it reports: the secrets in the settings (headers, cookies,
proxy login) are used but never shown, only their names are, and addresses are shown without
their tokens. Credentials are sent only to the address's own host and to the hosts the settings
allow, also across redirects.
"""

from __future__ import annotations

import concurrent.futures
import ipaddress
import socket
import ssl
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlsplit

import httpx

from rayohx.config import NetworkConfig, validate_url
from rayohx.redaction import is_sensitive_name, redact_url

if TYPE_CHECKING:
    from collections.abc import Callable

MAX_REDIRECTS = 10
SAMPLE_BYTES = 2048
_REDIRECTS = frozenset({301, 302, 303, 307, 308})


@dataclass(frozen=True, slots=True)
class NetworkStep:
    """One step of reaching a server."""

    name: str  # "dns", "connect", "tls" or "http"
    #: ``True`` it worked, ``False`` it failed, ``None`` it was not needed or not possible.
    ok: bool | None
    milliseconds: float | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "milliseconds": None if self.milliseconds is None else round(self.milliseconds, 1),
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class NetworkReport:
    """What happened on the way to a server."""

    url: str
    steps: tuple[NetworkStep, ...]
    redirects: tuple[tuple[str, int], ...] = ()
    status: int | None = None
    content_type: str | None = None
    looks_like_playlist: bool | None = None
    proxy: str = "none"
    tls: dict[str, Any] | None = None
    #: The header names that were sent (never their values).
    sent_headers: tuple[str, ...] = ()
    retries: int = 0
    #: ``None`` when everything worked, else a code such as ``DNS_FAILED`` or ``HTTP_403``.
    code: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.code is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "ok": self.ok,
            "code": self.code,
            "steps": [s.to_dict() for s in self.steps],
            "redirects": [{"url": u, "status": s} for u, s in self.redirects],
            "status": self.status,
            "content_type": self.content_type,
            "looks_like_playlist": self.looks_like_playlist,
            "proxy": self.proxy,
            "tls": self.tls,
            "sent_headers": list(self.sent_headers),
            "retries": self.retries,
            "notes": list(self.notes),
        }


def _timed(call: Callable[[], Any]) -> tuple[Any, float]:
    started = time.perf_counter()
    result = call()
    return result, (time.perf_counter() - started) * 1000


def _resolve(host: str, port: int, timeout: float, resolver: Callable[..., Any]) -> list[Any]:
    """Look a name up, giving up after ``timeout`` (the system call has no timeout of its own)."""
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(resolver, host, port, type=socket.SOCK_STREAM)
        try:
            return list(future.result(timeout))
        except concurrent.futures.TimeoutError:
            raise TimeoutError("the lookup timed out") from None
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _proxy_text(config: NetworkConfig) -> str:
    if config.proxy is not None:
        return f"configured ({config.proxy.redacted_url})"
    if config.proxy_from_env:
        return "from the environment"
    return "none"


def _verify(config: NetworkConfig) -> bool | str:
    verify = config.verify_tls
    return str(verify) if isinstance(verify, Path) else bool(verify)


def _tls_context(config: NetworkConfig) -> ssl.SSLContext:
    verify = config.verify_tls
    if verify is False:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    if isinstance(verify, Path):
        return ssl.create_default_context(cafile=str(verify))
    return ssl.create_default_context()


def _certificate_days(cert: dict[str, Any] | None) -> float | None:
    if not cert or "notAfter" not in cert:
        return None
    try:
        expires = ssl.cert_time_to_seconds(cert["notAfter"])
    except (ValueError, KeyError):
        return None
    return round((expires - time.time()) / 86400, 1)


def probe_network(
    url: str,
    config: NetworkConfig | None = None,
    *,
    timeout: float = 10.0,
    resolver: Callable[..., Any] = socket.getaddrinfo,
) -> NetworkReport:
    """Try to reach ``url`` and say how far we got.

    Raises:
        ConfigurationError: If ``url`` is not an http(s) address.
    """
    settings = config or NetworkConfig()
    address = validate_url(url)
    parts = urlsplit(address)
    host = parts.hostname or ""
    port = parts.port or (443 if parts.scheme == "https" else 80)
    proxied = settings.proxy is not None or settings.proxy_from_env
    steps: list[NetworkStep] = []
    notes: list[str] = []
    tls_info: dict[str, Any] | None = None
    shown = redact_url(address)

    def finish(code: str | None, **extra: Any) -> NetworkReport:
        return NetworkReport(
            url=shown,
            steps=tuple(steps),
            proxy=_proxy_text(settings),
            tls=tls_info,
            retries=settings.retries,
            code=code,
            notes=tuple(notes),
            **extra,
        )

    # 1. Name lookup. A proxy looks the name up itself, and an address needs no lookup.
    if proxied or _is_ip(host):
        steps.append(
            NetworkStep(
                "dns", None, None, "not needed" + (" (the proxy looks it up)" if proxied else "")
            )
        )
    else:
        try:
            found, ms = _timed(lambda: _resolve(host, port, timeout, resolver))
        except (OSError, TimeoutError) as exc:
            steps.append(NetworkStep("dns", False, None, str(exc) or "the name was not found"))
            return finish("DNS_FAILED")
        steps.append(NetworkStep("dns", True, ms, f"{len(found)} address(es)"))

    # 2. Connecting.
    if proxied:
        steps.append(NetworkStep("connect", None, None, "made by the proxy"))
        sock = None
    else:
        try:
            sock, ms = _timed(lambda: socket.create_connection((host, port), timeout))
        except TimeoutError:
            steps.append(NetworkStep("connect", False, None, "no answer in time"))
            return finish("CONNECT_TIMEOUT")
        except OSError as exc:
            steps.append(NetworkStep("connect", False, None, exc.strerror or "refused"))
            return finish("CONNECT_FAILED")
        steps.append(NetworkStep("connect", True, ms, ""))

    # 3. The secure handshake.
    if parts.scheme != "https":
        steps.append(NetworkStep("tls", None, None, "plain http"))
        if sock is not None:
            sock.close()
    elif sock is None:
        steps.append(NetworkStep("tls", None, None, "made by the proxy"))
    else:
        try:
            context = _tls_context(settings)
            wrapped, ms = _timed(lambda: context.wrap_socket(sock, server_hostname=host))
        except ssl.SSLError as exc:
            sock.close()
            reason = getattr(exc, "verify_message", None) or exc.reason or str(exc)
            steps.append(NetworkStep("tls", False, None, str(reason)))
            return finish("TLS_FAILED")
        except OSError as exc:
            sock.close()
            steps.append(NetworkStep("tls", False, None, exc.strerror or "the handshake failed"))
            return finish("TLS_FAILED")
        tls_info = {
            "version": wrapped.version(),
            "verified": settings.verify_tls is not False,
            "certificate_days_left": _certificate_days(wrapped.getpeercert()),
        }
        wrapped.close()
        steps.append(NetworkStep("tls", True, ms, wrapped.version() or ""))
        if settings.verify_tls is False:
            notes.append("Certificate checking is switched off in the settings.")

    # 4. Asking for the address, following redirects by hand so secrets stay with their host.
    secret_headers = {k: v for k, v in settings.request_headers().items() if is_sensitive_name(k)}
    plain_headers = {k: v for k, v in settings.request_headers().items() if k not in secret_headers}
    allowed = {host.lower(), *settings.credential_hosts}
    hops: list[tuple[str, int]] = []
    current = address
    started = time.perf_counter()
    sent: set[str] = set()
    try:
        with httpx.Client(
            verify=_verify(settings),
            proxy=settings.proxy.url if settings.proxy else None,
            trust_env=settings.proxy_from_env,
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                here = (urlsplit(current).hostname or "").lower()
                headers = dict(plain_headers)
                cookies: dict[str, str] = {}
                if here in allowed:
                    headers.update(secret_headers)
                    cookies = dict(settings.cookies)
                sent |= set(headers) | ({"Cookie"} if cookies else set())
                with client.stream("GET", current, headers=headers, cookies=cookies) as response:
                    if response.status_code in _REDIRECTS and "location" in response.headers:
                        hops.append((redact_url(current), response.status_code))
                        current = urljoin(current, response.headers["location"])
                        if urlsplit(current).scheme not in {"http", "https"}:
                            steps.append(
                                NetworkStep("http", False, None, "redirected somewhere odd")
                            )
                            return finish("RESPONSE_INVALID", redirects=tuple(hops))
                        continue
                    ms = (time.perf_counter() - started) * 1000
                    body = b""
                    for chunk in response.iter_bytes():
                        body += chunk
                        if len(body) >= SAMPLE_BYTES:
                            break
                    status = response.status_code
                    ctype = response.headers.get("content-type")
                    playlist = body.lstrip(b"\xef\xbb\xbf").lstrip().startswith(b"#EXTM3U")
                    steps.append(NetworkStep("http", status < 400, ms, f"HTTP {status}"))
                    extra = {
                        "redirects": tuple(hops),
                        "status": status,
                        "content_type": ctype,
                        "looks_like_playlist": playlist,
                        "sent_headers": tuple(sorted(sent)),
                    }
                    if status in {401, 403}:
                        return finish(f"AUTH_{status}", **extra)
                    if status >= 400:
                        return finish(f"HTTP_{status}", **extra)
                    if not playlist:
                        notes.append("The answer does not start like an HLS playlist.")
                        return finish("NOT_A_PLAYLIST", **extra)
                    return finish(None, **extra)
            steps.append(NetworkStep("http", False, None, "too many redirects"))
            return finish("RESPONSE_INVALID", redirects=tuple(hops))
    except httpx.TimeoutException:
        steps.append(NetworkStep("http", False, None, "no answer in time"))
        return finish("NETWORK_TIMEOUT", redirects=tuple(hops), sent_headers=tuple(sorted(sent)))
    except httpx.ProxyError as exc:
        steps.append(NetworkStep("http", False, None, f"the proxy failed: {exc}"))
        return finish("NETWORK_CONNECTION", redirects=tuple(hops))
    except httpx.HTTPError as exc:
        steps.append(NetworkStep("http", False, None, type(exc).__name__))
        return finish("NETWORK_CONNECTION", redirects=tuple(hops), sent_headers=tuple(sorted(sent)))
