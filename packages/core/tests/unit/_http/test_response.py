from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
from rayohx_pytest.mocks import Body, ok, sequence

from rayohx import SegmentRange
from rayohx._http._common import MAX_RETRY_AFTER
from rayohx.errors import (
    AuthenticationError,
    HTTPError,
    InvalidResponseError,
    NetworkError,
    PlaylistNotFoundError,
)
from tests.helpers.http import URL, make


def test_redirects_are_followed_and_the_final_address_reported() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/vod/a.ts":
            return httpx.Response(302, headers={"location": "/moved/b.ts"})
        return httpx.Response(200, content=b"payload")

    client, recorder, _ = make(handler)
    assert client.fetch_bytes(URL).url == "https://media.example.com/moved/b.ts"
    assert len(recorder.requests) == 2


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_every_redirect_status_is_followed(status: int) -> None:
    queue = [httpx.Response(status, headers={"location": "https://other.example.net/x"})]

    def handler(_request: httpx.Request) -> httpx.Response:
        return queue.pop(0) if queue else httpx.Response(200, content=b"x")

    client, _, _ = make(handler)
    assert client.fetch_bytes(URL).url == "https://other.example.net/x"


def test_a_redirect_loop_stops() -> None:
    client, recorder, _ = make(
        lambda _r: httpx.Response(302, headers={"location": "/again"}), max_redirects=3
    )
    with pytest.raises(NetworkError, match="Too many redirects"):
        client.fetch_bytes(URL)
    assert len(recorder.requests) == 4


@pytest.mark.parametrize(
    "response",
    [httpx.Response(302), httpx.Response(302, headers={"location": "ftp://host/file"})],
)
def test_broken_redirects_are_rejected(response: httpx.Response) -> None:
    client, _, _ = make(lambda _r: response)
    with pytest.raises(InvalidResponseError):
        client.fetch_bytes(URL)


def test_a_byte_range_is_requested_and_checked() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            206, content=b"0123456789", headers={"content-range": "bytes 5-14/100"}
        )

    client, recorder, _ = make(handler)
    response = client.fetch_bytes(URL, byte_range=SegmentRange(10, 5))
    assert response.content == b"0123456789"
    assert recorder.requests[0].headers["range"] == "bytes=5-14"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(206, content=b"0123456789", headers={"content-range": "bytes 0-9/100"}),
        httpx.Response(206, content=b"0123456789"),
        httpx.Response(200, content=b"0123456789"),
    ],
)
def test_wrong_or_missing_range_answers_are_rejected_without_retrying(
    response: httpx.Response,
) -> None:
    client, recorder, _ = make(lambda _r: response)
    with pytest.raises(InvalidResponseError) as info:
        client.fetch_bytes(URL, byte_range=SegmentRange(10, 5))
    assert not info.value.retryable
    assert len(recorder.requests) == 1


def test_a_short_range_body_is_retried() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(206, content=b"01234", headers={"content-range": "bytes 5-14/100"})

    client, recorder, _ = make(handler, retries=1)
    with pytest.raises(InvalidResponseError, match="Expected 10 bytes"):
        client.fetch_bytes(URL, byte_range=SegmentRange(10, 5))
    assert len(recorder.requests) == 2


def test_a_range_without_an_offset_cannot_be_requested() -> None:
    client, _, _ = make(ok())
    with pytest.raises(ValueError, match="offset"):
        client.fetch_bytes(URL, byte_range=SegmentRange(10))


@pytest.mark.parametrize("status", [400, 404, 410, 416])
def test_client_errors_are_not_retried(status: int) -> None:
    client, recorder, fake = make(lambda _r: httpx.Response(status))
    with pytest.raises(HTTPError) as info:
        client.fetch_bytes(URL)
    assert info.value.status_code == status
    assert not info.value.retryable
    assert len(recorder.requests) == 1
    assert fake.sleeps == []


@pytest.mark.parametrize("status", [401, 403])
def test_refused_credentials_raise_authentication_errors(status: int) -> None:
    client, recorder, _ = make(lambda _r: httpx.Response(status))
    with pytest.raises(AuthenticationError) as info:
        client.fetch_bytes(URL)
    assert info.value.hint
    assert len(recorder.requests) == 1


@pytest.mark.parametrize("status", [404, 410])
def test_a_missing_playlist_has_its_own_error(status: int) -> None:
    client, _, _ = make(lambda _r: httpx.Response(status))
    with pytest.raises(PlaylistNotFoundError):
        client.fetch_text(URL)


def test_other_playlist_errors_stay_http_errors() -> None:
    client, _, _ = make(lambda _r: httpx.Response(403))
    with pytest.raises(AuthenticationError):
        client.fetch_text(URL)


def test_retry_after_seconds_is_honoured() -> None:
    client, _, fake = make(
        sequence(
            httpx.Response(429, headers={"retry-after": "7"}), httpx.Response(200, content=b"x")
        )
    )
    client.fetch_bytes(URL)
    assert fake.sleeps == [7.0]


def test_retry_after_is_capped() -> None:
    client, _, fake = make(
        sequence(
            httpx.Response(503, headers={"retry-after": "3600"}), httpx.Response(200, content=b"x")
        )
    )
    client.fetch_bytes(URL)
    assert fake.sleeps == [MAX_RETRY_AFTER]


def test_retry_after_dates_are_understood() -> None:
    when = format_datetime(datetime.now(UTC) + timedelta(seconds=30), usegmt=True)
    client, _, fake = make(
        sequence(
            httpx.Response(503, headers={"retry-after": when}), httpx.Response(200, content=b"x")
        )
    )
    client.fetch_bytes(URL)
    assert 25 < fake.sleeps[0] <= 30


def test_unreadable_retry_after_falls_back_to_backoff() -> None:
    client, _, fake = make(
        sequence(
            httpx.Response(503, headers={"retry-after": "soon"}), httpx.Response(200, content=b"x")
        ),
        backoff_factor=1.0,
    )
    client.fetch_bytes(URL)
    assert 0.75 <= fake.sleeps[0] <= 1.25


def test_web_pages_served_as_media_are_retried_then_reported() -> None:
    client, recorder, _ = make(ok(b"<h1>Denied</h1>", **{"content-type": "text/html"}), retries=2)
    with pytest.raises(InvalidResponseError, match="web page") as info:
        client.fetch_bytes(URL)
    assert info.value.retryable
    assert info.value.hint
    assert len(recorder.requests) == 3


def test_web_pages_with_a_media_content_type_are_caught_by_their_content() -> None:
    page = b"  <!DOCTYPE html><html><body>expired</body></html>"
    client, _, _ = make(ok(page, **{"content-type": "application/octet-stream"}), retries=0)
    with pytest.raises(InvalidResponseError, match="web page"):
        client.fetch_bytes(URL)


def test_empty_bodies_are_errors() -> None:
    client, recorder, _ = make(ok(b""), retries=1)
    with pytest.raises(InvalidResponseError, match="empty"):
        client.fetch_bytes(URL)
    assert len(recorder.requests) == 2


def test_cut_off_bodies_are_errors_and_retried() -> None:
    cut = httpx.Response(200, content=b"x" * 50, headers={"content-length": "100"})
    client, recorder, _ = make(sequence(cut, httpx.Response(200, content=b"y" * 100)))
    assert client.fetch_bytes(URL).content == b"y" * 100
    assert len(recorder.requests) == 2


def test_cut_off_bodies_that_never_recover_raise() -> None:
    client, _, _ = make(
        lambda _r: httpx.Response(200, content=b"x" * 50, headers={"content-length": "100"}),
        retries=1,
    )
    with pytest.raises(InvalidResponseError, match="cut short"):
        client.fetch_bytes(URL)


def test_oversized_responses_are_rejected_without_retrying() -> None:
    client, recorder, _ = make(ok(b"x" * 20))
    with pytest.raises(InvalidResponseError, match="larger") as info:
        client.fetch_bytes(URL, max_bytes=10)
    assert not info.value.retryable
    assert len(recorder.requests) == 1


def test_oversized_streams_without_a_declared_length_are_rejected() -> None:
    response = httpx.Response(200, stream=Body([b"x" * 40_000, b"x" * 40_000]))
    client, _, _ = make(lambda _r: response)
    with pytest.raises(InvalidResponseError, match="larger"):
        client.fetch_bytes(URL, max_bytes=50_000)
