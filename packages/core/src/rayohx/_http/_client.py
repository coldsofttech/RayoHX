"""The HTTP layer. Every network request the engine makes goes through ``HttpClient``.

It builds on ``httpx`` and adds what a downloader needs on top: retries with back-off, redirects
handled one hop at a time (so credentials never follow a redirect to another host), response
checks that catch web pages and cut-off bodies served with a success status, a shared speed limit,
an overall time limit and cooperative cancellation.

Credentials are scoped. Secret headers (``Authorization``, ``Cookie``, API keys) and the
configured cookies go only to the host the download started from and to ``credential_hosts``.
Other headers, such as ``Referer``, ``Origin`` and ``User-Agent``, go everywhere because CDNs
often need them.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from rayohx._http._common import (
    CHUNK_SIZE,
    DEFAULT_MAX_BYTES,
    DEFAULT_POOL_SIZE,
    MAX_PLAYLIST_BYTES,
    MAX_RETRY_AFTER,
    environment_proxies,
    host_of,
    proxy_url,
    tls_context,
    translate,
)
from rayohx._http._response import (
    HttpResponse,
    check_content_range,
    check_status,
    declared_length,
    is_redirect,
    is_web_page_type,
    looks_like_web_page,
    redirect_target,
)
from rayohx._logs import get_logger
from rayohx._redaction import is_sensitive_name, redact_url
from rayohx.config import validate_url
from rayohx.errors import (
    HTTPError,
    InvalidResponseError,
    NetworkError,
    NetworkTimeoutError,
    PlaylistNotFoundError,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType
    from typing import Self

    import httpx

    from rayohx._ratelimit import RateLimiter
    from rayohx.cancellation import CancellationToken
    from rayohx.config import NetworkConfig
    from rayohx.models import SegmentRange

logger = get_logger("http")


class HttpClient:
    """Fetches playlists, keys and segments. Safe to share between worker threads.

    Args:
        config: Timeouts, retries, headers, cookies, proxy, TLS and speed limit.
        origin_url: The address the download starts from. Its host may receive credentials. If
            omitted, the host of the first request is used.
        cancel: Stops waiting and reading as soon as it is cancelled.
        pool_size: Most connections kept open to the servers.
        transport: A replacement ``httpx`` transport, for tests.
        url_guard: Called with every address before it is requested, including redirect
            targets. It can raise to refuse an address, which is where a server deployment
            would block private networks.
    """

    def __init__(
        self,
        config: NetworkConfig,
        *,
        origin_url: str | None = None,
        cancel: CancellationToken | None = None,
        pool_size: int = DEFAULT_POOL_SIZE,
        transport: httpx.BaseTransport | None = None,
        url_guard: Callable[[str], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        import random
        import threading

        import httpx

        self._config = config
        self._cancel = cancel
        self._guard = url_guard
        self._sleep = sleep
        self._clock = clock
        self._random = random.Random()  # noqa: S311 - retry jitter, not security
        self._limiter: RateLimiter | None = None
        if config.rate_limit:
            from rayohx._ratelimit import RateLimiter

            self._limiter = RateLimiter(config.rate_limit, clock=clock, sleep=sleep)

        self._trust_lock = threading.Lock()
        self._trusted = set(config.credential_hosts)
        self._adopt_first_host = origin_url is None
        if origin_url is not None:
            self._trusted.add(host_of(origin_url))

        if config.verify_tls is False:
            logger.warning("TLS certificate verification is turned off.")
        timeout = httpx.Timeout(
            connect=config.connect_timeout,
            read=config.read_timeout,
            write=config.read_timeout,
            pool=config.connect_timeout,
        )
        limits = httpx.Limits(max_connections=pool_size, max_keepalive_connections=pool_size)
        tls = tls_context(
            config.verify_tls, config.client_cert, config.client_key, config.client_key_password
        )
        mounts: dict[str, httpx.BaseTransport | None] = {}
        if config.proxy is None and config.proxy_from_env and transport is None:
            proxies, no_proxy = environment_proxies()
            for scheme, found in proxies.items():
                mounts[f"{scheme}://"] = httpx.HTTPTransport(
                    verify=tls, limits=limits, proxy=proxy_url(found)
                )
            if proxies:
                for entry in no_proxy:
                    if entry == "*":
                        mounts["all://"] = None
                        continue
                    host = entry.lstrip("*").lstrip(".").split(":")[0]
                    if host and "/" not in host and "[" not in host:  # no CIDR ranges or IPv6
                        mounts[f"all://{host}"] = None
                        mounts[f"all://*.{host}"] = None
        self._client = httpx.Client(
            transport=transport,
            mounts=mounts or None,
            timeout=timeout,
            limits=limits,
            verify=tls,
            proxy=proxy_url(config.proxy) if config.proxy else None,
            follow_redirects=False,  # redirects are followed here, hop by hop
            trust_env=False,  # settings come from the config, never from hidden variables
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close every open connection."""
        self._client.close()

    # --- public requests -------------------------------------------------------------------

    def fetch_text(self, url: str) -> tuple[str, str]:
        """Fetch a playlist. Returns its text and the address it finally came from.

        Raises:
            PlaylistNotFoundError: If the server says the playlist does not exist.
        """
        try:
            response = self._get(
                url,
                accept_encoding="gzip, deflate",
                max_bytes=MAX_PLAYLIST_BYTES,
                expect_media=False,
            )
        except HTTPError as exc:
            if exc.status_code in {404, 410}:
                raise PlaylistNotFoundError(
                    f"The playlist was not found: {exc.url}",
                    hint="Check the address; the link may have expired.",
                ) from exc
            raise
        return response.content.decode("utf-8", errors="replace"), response.url

    def fetch_bytes(
        self,
        url: str,
        *,
        byte_range: SegmentRange | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        on_bytes: Callable[[int], None] | None = None,
    ) -> HttpResponse:
        """Fetch a key, an initialization section or a segment, or part of one.

        ``on_bytes`` is told the size of each chunk as it arrives, including chunks of an
        attempt that is later retried.
        """
        return self._get(
            url,
            accept_encoding="identity",
            max_bytes=max_bytes,
            expect_media=True,
            byte_range=byte_range,
            on_bytes=on_bytes,
        )

    # --- retries ---------------------------------------------------------------------------

    def _get(
        self,
        url: str,
        *,
        accept_encoding: str,
        max_bytes: int,
        expect_media: bool,
        byte_range: SegmentRange | None = None,
        on_bytes: Callable[[int], None] | None = None,
    ) -> HttpResponse:
        url = validate_url(url, name="request address")
        total = self._config.total_timeout
        deadline = None if total is None else self._clock() + total
        attempts = self._config.retries + 1
        for attempt in range(1, attempts + 1):
            self._raise_if_cancelled()
            try:
                return self._attempt(
                    url,
                    accept_encoding=accept_encoding,
                    max_bytes=max_bytes,
                    expect_media=expect_media,
                    byte_range=byte_range,
                    on_bytes=on_bytes,
                    deadline=deadline,
                )
            except NetworkError as exc:
                if not exc.retryable or attempt == attempts:
                    raise
                delay = self._delay(attempt, exc)
                if deadline is not None and self._clock() + delay >= deadline:
                    raise
                logger.warning(
                    "Attempt %d of %d failed (%s). Retrying %s in %.1fs.",
                    attempt,
                    attempts,
                    exc.message,
                    url,
                    delay,
                )
                self._pause(delay)
        raise AssertionError  # pragma: no cover - the last attempt always returns or raises

    def _delay(self, attempt: int, error: NetworkError) -> float:
        if isinstance(error, HTTPError) and error.retry_after is not None:
            return min(error.retry_after, MAX_RETRY_AFTER)
        base = self._config.backoff_factor * 2 ** (attempt - 1)
        jitter: float = self._random.uniform(0.75, 1.25)
        return float(base * jitter)

    def _pause(self, seconds: float) -> None:
        if seconds <= 0:
            return
        if self._cancel is not None:
            if self._cancel.wait(seconds):
                self._cancel.raise_if_cancelled()
        else:
            self._sleep(seconds)

    def _raise_if_cancelled(self) -> None:
        if self._cancel is not None:
            self._cancel.raise_if_cancelled()

    # --- one attempt -----------------------------------------------------------------------

    def _attempt(
        self,
        url: str,
        *,
        accept_encoding: str,
        max_bytes: int,
        expect_media: bool,
        byte_range: SegmentRange | None,
        on_bytes: Callable[[int], None] | None,
        deadline: float | None,
    ) -> HttpResponse:
        import httpx

        current = url
        for _hop in range(self._config.max_redirects + 1):
            if self._guard is not None:
                self._guard(current)
            headers = self._headers_for(current, accept_encoding, byte_range)
            try:
                with self._client.stream("GET", current, headers=headers) as response:
                    if is_redirect(response):
                        current = redirect_target(response, current)
                        continue
                    check_status(response, current, byte_range)
                    return self._read(
                        response,
                        current,
                        max_bytes=max_bytes,
                        expect_media=expect_media,
                        byte_range=byte_range,
                        on_bytes=on_bytes,
                        deadline=deadline,
                    )
            except (httpx.HTTPError, httpx.InvalidURL, httpx.StreamError) as exc:
                raise translate(exc, current) from exc
        raise NetworkError(
            f"Too many redirects (more than {self._config.max_redirects}) for {redact_url(url)}.",
            hint="The address may redirect in a loop.",
        )

    def _read(
        self,
        response: httpx.Response,
        url: str,
        *,
        max_bytes: int,
        expect_media: bool,
        byte_range: SegmentRange | None,
        on_bytes: Callable[[int], None] | None,
        deadline: float | None,
    ) -> HttpResponse:
        shown = redact_url(url)
        content_type = response.headers.get("content-type", "")
        if expect_media and is_web_page_type(content_type):
            raise InvalidResponseError(
                f"The server sent a web page instead of media: {shown}",
                hint="The link may have expired or may need sign-in. Check headers and cookies.",
                retryable=True,
            )
        declared = declared_length(response)
        if declared is not None and declared > max_bytes:
            raise InvalidResponseError(
                f"The response is larger than the allowed {max_bytes} bytes."
            )
        if byte_range is not None:
            check_content_range(response, byte_range, shown)

        chunks: list[bytes] = []
        received = 0
        for chunk in response.iter_bytes(CHUNK_SIZE):
            self._raise_if_cancelled()
            if deadline is not None and self._clock() >= deadline:
                raise NetworkTimeoutError(
                    f"The overall time limit ran out while downloading {shown}", retryable=False
                )
            if self._limiter is not None:
                self._limiter.acquire(len(chunk), self._cancel)
            received += len(chunk)
            if received > max_bytes:
                raise InvalidResponseError(
                    f"The response is larger than the allowed {max_bytes} bytes."
                )
            chunks.append(chunk)
            if on_bytes is not None:
                on_bytes(len(chunk))

        # Compressed bodies are length-checked by the HTTP library itself; for plain bodies the
        # bytes received are the bytes on the wire.
        plain = response.headers.get("content-encoding", "identity").lower() in {"", "identity"}
        if declared is not None and plain and received != declared:
            raise InvalidResponseError(
                f"The response was cut short ({received} of {declared} bytes): {shown}",
                retryable=True,
            )
        if received == 0:
            raise InvalidResponseError(
                f"The server sent an empty response: {shown}", retryable=True
            )
        if byte_range is not None and received != byte_range.length:
            raise InvalidResponseError(
                f"Expected {byte_range.length} bytes but received {received}: {shown}",
                retryable=True,
            )
        content = b"".join(chunks)
        if expect_media and looks_like_web_page(content):
            raise InvalidResponseError(
                f"The server sent a web page instead of media: {shown}",
                hint="The link may have expired or may need sign-in. Check headers and cookies.",
                retryable=True,
            )
        return HttpResponse(
            url=url,
            status_code=response.status_code,
            headers={name.lower(): value for name, value in response.headers.items()},
            content=content,
        )

    # --- headers and credentials -----------------------------------------------------------

    def _is_trusted(self, host: str) -> bool:
        with self._trust_lock:
            if self._adopt_first_host:
                self._trusted.add(host)
                self._adopt_first_host = False
            return host in self._trusted

    def _headers_for(
        self, url: str, accept_encoding: str, byte_range: SegmentRange | None
    ) -> dict[str, str]:
        trusted = self._is_trusted(host_of(url))
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
