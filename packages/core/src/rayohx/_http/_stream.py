"""Reads a response body with the size, time, speed and integrity checks a downloader needs."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx

    from rayohx._http._response import HttpResponse
    from rayohx._ratelimit import RateLimiter
    from rayohx.cancellation import CancellationToken
    from rayohx.models import SegmentRange


def read_body(
    response: httpx.Response,
    url: str,
    *,
    max_bytes: int,
    expect_media: bool,
    byte_range: SegmentRange | None,
    on_bytes: Callable[[int], None] | None,
    deadline: float | None,
    clock: Callable[[], float],
    limiter: RateLimiter | None,
    cancel: CancellationToken | None,
) -> HttpResponse:
    """Read ``response`` in full, refusing web pages, cut-off bodies and oversized ones.

    Cancellation, the overall ``deadline`` and the shared speed limit are checked between chunks.
    """
    from rayohx._http._common import CHUNK_SIZE
    from rayohx._http._response import (
        HttpResponse,
        check_content_range,
        declared_length,
        is_web_page_type,
        looks_like_web_page,
    )
    from rayohx._redaction import redact_url
    from rayohx.errors import InvalidResponseError, NetworkTimeoutError

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
        raise InvalidResponseError(f"The response is larger than the allowed {max_bytes} bytes.")
    if byte_range is not None:
        check_content_range(response, byte_range, shown)

    chunks: list[bytes] = []
    received = 0
    for chunk in response.iter_bytes(CHUNK_SIZE):
        if cancel is not None:
            cancel.raise_if_cancelled()
        if deadline is not None and clock() >= deadline:
            raise NetworkTimeoutError(
                f"The overall time limit ran out while downloading {shown}", retryable=False
            )
        if limiter is not None:
            limiter.acquire(len(chunk), cancel)
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
        raise InvalidResponseError(f"The server sent an empty response: {shown}", retryable=True)
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
