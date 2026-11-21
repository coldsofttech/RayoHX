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

from rayohx._logs import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType
    from typing import Self

    import httpx

    from rayohx._http._credentials import CredentialScope
    from rayohx._http._response import HttpResponse
    from rayohx._ratelimit import RateLimiter
    from rayohx.cancellation import CancellationToken
    from rayohx.config import NetworkConfig
    from rayohx.errors import NetworkError
    from rayohx.models import SegmentRange

logger = get_logger("http")


class HttpClient:
    """Fetches playlists, keys and segments. Safe to share between worker threads.

    Args:
        config: Timeouts, retries, headers, cookies, proxy, TLS and speed limit.
        origin_url: The address the download starts from. Its host may receive credentials. If
            omitted, the host of the first request is used.
        cancel: Stops waiting and reading as soon as it is cancelled.
        pool_size: Most connections kept open to the servers. Defaults to 16.
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
        pool_size: int | None = None,
        transport: httpx.BaseTransport | None = None,
        url_guard: Callable[[str], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        import random

        from rayohx._http._common import DEFAULT_POOL_SIZE
        from rayohx._http._credentials import CredentialScope
        from rayohx._http._transport import build_client

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

        self._credentials: CredentialScope = CredentialScope(config, origin_url)
        if config.verify_tls is False:
            logger.warning("TLS certificate verification is turned off.")
        self._client = build_client(
            config,
            pool_size=DEFAULT_POOL_SIZE if pool_size is None else pool_size,
            transport=transport,
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
        from rayohx._http._common import MAX_PLAYLIST_BYTES
        from rayohx.errors import HTTPError, PlaylistNotFoundError

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
        max_bytes: int | None = None,
        on_bytes: Callable[[int], None] | None = None,
    ) -> HttpResponse:
        """Fetch a key, an initialization section or a segment, or part of one.

        ``on_bytes`` is told the size of each chunk as it arrives, including chunks of an
        attempt that is later retried. ``max_bytes`` defaults to 512 MiB.
        """
        from rayohx._http._common import DEFAULT_MAX_BYTES

        return self._get(
            url,
            accept_encoding="identity",
            max_bytes=DEFAULT_MAX_BYTES if max_bytes is None else max_bytes,
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
        from rayohx.config import validate_url
        from rayohx.errors import NetworkError

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
        from rayohx._http._common import MAX_RETRY_AFTER
        from rayohx.errors import HTTPError

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

        from rayohx._http._common import translate
        from rayohx._http._response import check_status, is_redirect, redirect_target
        from rayohx._http._stream import read_body
        from rayohx._redaction import redact_url
        from rayohx.errors import NetworkError

        current = url
        for _hop in range(self._config.max_redirects + 1):
            if self._guard is not None:
                self._guard(current)
            headers = self._credentials.headers_for(current, accept_encoding, byte_range)
            try:
                with self._client.stream("GET", current, headers=headers) as response:
                    if is_redirect(response):
                        current = redirect_target(response, current)
                        continue
                    check_status(response, current, byte_range)
                    return read_body(
                        response,
                        current,
                        max_bytes=max_bytes,
                        expect_media=expect_media,
                        byte_range=byte_range,
                        on_bytes=on_bytes,
                        deadline=deadline,
                        clock=self._clock,
                        limiter=self._limiter,
                        cancel=self._cancel,
                    )
            except (httpx.HTTPError, httpx.InvalidURL, httpx.StreamError) as exc:
                raise translate(exc, current) from exc
        raise NetworkError(
            f"Too many redirects (more than {self._config.max_redirects}) for {redact_url(url)}.",
            hint="The address may redirect in a loop.",
        )
