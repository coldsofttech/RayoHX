"""What comes back: the response type and the checks that catch bad responses."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

import httpx

from rayohx._redaction import redact_url
from rayohx.errors import AuthenticationError, HTTPError, InvalidResponseError
from rayohx.models import SegmentRange

_REDIRECTS = frozenset({301, 302, 303, 307, 308})
_CONTENT_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+|\*)$")
_WEB_PAGE = re.compile(rb"^\s*(<!doctype\s+html|<html|<head|<body)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """A complete, validated response."""

    url: str
    status_code: int
    headers: Mapping[str, str]
    content: bytes


def is_redirect(response: httpx.Response) -> bool:
    """Whether the server answered with a redirect."""
    return response.status_code in _REDIRECTS


def redirect_target(response: httpx.Response, current: str) -> str:
    """The absolute address a redirect points to."""
    location = response.headers.get("location")
    if not location:
        raise InvalidResponseError(f"A redirect from {redact_url(current)} has no destination.")
    target: str = urljoin(current, location)
    if urlsplit(target).scheme.lower() not in {"http", "https"}:
        raise InvalidResponseError(
            f"{redact_url(current)} redirects to an unsupported address: {redact_url(target)}"
        )
    return target


def retry_after(response: httpx.Response) -> float | None:
    """Seconds the server asked to wait (``Retry-After``), or ``None``."""
    value = response.headers.get("retry-after")
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return max(0.0, (moment - datetime.now(UTC)).total_seconds())


def check_status(response: httpx.Response, url: str, byte_range: SegmentRange | None) -> None:
    """Raise the matching error unless the status is a success (206 when a range was asked)."""
    status = response.status_code
    if status in {401, 403}:
        raise AuthenticationError(
            url,
            status,
            hint="The server refused the request. Check the Authorization header, cookies, "
            "Referer and Origin.",
        )
    if status >= 300 or status < 200:
        raise HTTPError(url, status, retry_after=retry_after(response))
    if byte_range is not None and status != 206:
        raise InvalidResponseError(
            f"The server ignored the byte range request (HTTP {status}): {redact_url(url)}",
            hint="This stream needs a server that supports ranges.",
        )


def declared_length(response: httpx.Response) -> int | None:
    """The ``Content-Length`` the server declared, or ``None``."""
    value = response.headers.get("content-length")
    return int(value) if value and value.isdigit() else None


def check_content_range(response: httpx.Response, requested: SegmentRange, shown: str) -> None:
    """Raise unless the server returned exactly the byte range that was requested."""
    match = _CONTENT_RANGE.match(response.headers.get("content-range", "").strip())
    start = requested.offset
    if start is None:
        raise ValueError("a byte range needs an offset before it can be requested")
    expected = (start, start + requested.length - 1)
    if not match or (int(match.group(1)), int(match.group(2))) != expected:
        raise InvalidResponseError(
            f"The server returned a different byte range than requested: {shown}"
        )


def is_web_page_type(content_type: str) -> bool:
    """Whether a ``Content-Type`` says the body is a web page."""
    return content_type.lower().startswith(("text/html", "application/xhtml"))


def looks_like_web_page(content: bytes) -> bool:
    """Whether the start of a body is HTML, which a media request should never get."""
    return _WEB_PAGE.match(content[:512]) is not None
