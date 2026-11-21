import gzip

import httpx
import pytest

from rayohx import CancellationToken
from rayohx.errors import (
    CancellationError,
    ConfigurationError,
    HTTPError,
)
from tests.helpers.http import URL, make, ok, sequence


def test_fetch_text_returns_text_and_address() -> None:
    client, recorder, _ = make(ok(b"#EXTM3U\n"))
    assert client.fetch_text(URL) == ("#EXTM3U\n", URL)
    request = recorder.requests[0]
    assert request.headers["user-agent"] == "RayoHX"
    assert request.headers["accept-encoding"] == "gzip, deflate"


def test_fetch_text_decodes_compressed_playlists() -> None:
    body = gzip.compress(b"#EXTM3U\n#EXT-X-VERSION:3\n")
    client, _, _ = make(ok(body, **{"content-encoding": "gzip"}))
    assert client.fetch_text(URL)[0] == "#EXTM3U\n#EXT-X-VERSION:3\n"


def test_fetch_text_survives_invalid_utf8() -> None:
    client, _, _ = make(ok(b"#EXTM3U\n\xff\xfe"))
    assert client.fetch_text(URL)[0].startswith("#EXTM3U")


def test_fetch_text_hands_back_web_pages_for_the_parser_to_reject() -> None:
    client, _, _ = make(ok(b"<html></html>", **{"content-type": "text/html"}))
    assert client.fetch_text(URL)[0] == "<html></html>"


def test_fetch_bytes_asks_for_uncompressed_data() -> None:
    client, recorder, _ = make(ok(b"\x47" * 188, **{"content-type": "video/mp2t"}))
    response = client.fetch_bytes(URL)
    assert response.content == b"\x47" * 188
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp2t"
    assert recorder.requests[0].headers["accept-encoding"] == "identity"


def test_invalid_addresses_are_refused_before_any_request() -> None:
    client, recorder, _ = make(ok())
    with pytest.raises(ConfigurationError):
        client.fetch_bytes("ftp://example.com/a.ts")
    assert recorder.requests == []


def test_the_client_is_a_context_manager() -> None:
    with make(ok())[0] as client:
        client.fetch_bytes(URL)
    assert client._client.is_closed


def test_the_address_guard_sees_every_hop_and_can_refuse() -> None:
    seen: list[str] = []

    def guard(url: str) -> None:
        seen.append(url)
        if "internal" in url:
            raise ConfigurationError("Private addresses are not allowed.")

    handler = sequence(
        httpx.Response(302, headers={"location": "http://internal.local/secret"}),
    )
    client, recorder, _ = make(handler, url_guard=guard)
    with pytest.raises(ConfigurationError, match="Private"):
        client.fetch_bytes(URL)
    assert seen == [URL, "http://internal.local/secret"]
    assert len(recorder.requests) == 1


@pytest.mark.parametrize("status", [408, 425, 429, 500, 502, 503, 504])
def test_temporary_errors_are_retried_until_they_clear(status: int) -> None:
    client, recorder, fake = make(
        sequence(httpx.Response(status), httpx.Response(200, content=b"ok"))
    )
    assert client.fetch_bytes(URL).content == b"ok"
    assert len(recorder.requests) == 2
    assert len(fake.sleeps) == 1


def test_retries_stop_after_the_configured_count() -> None:
    client, recorder, fake = make(lambda _r: httpx.Response(503), retries=3, backoff_factor=0.5)
    with pytest.raises(HTTPError) as info:
        client.fetch_bytes(URL)
    assert info.value.retryable
    assert len(recorder.requests) == 4
    assert len(fake.sleeps) == 3
    for number, delay in enumerate(fake.sleeps):
        expected = 0.5 * 2**number
        assert expected * 0.75 <= delay <= expected * 1.25


def test_zero_retries_means_one_attempt() -> None:
    client, recorder, _ = make(lambda _r: httpx.Response(500), retries=0)
    with pytest.raises(HTTPError):
        client.fetch_bytes(URL)
    assert len(recorder.requests) == 1


def test_a_retry_that_would_pass_the_overall_limit_is_not_attempted() -> None:
    client, recorder, fake = make(
        lambda _r: httpx.Response(503), total_timeout=5, backoff_factor=10, retries=3
    )
    with pytest.raises(HTTPError):
        client.fetch_bytes(URL)
    assert len(recorder.requests) == 1
    assert fake.sleeps == []


def test_cancelled_before_starting_sends_nothing() -> None:
    token = CancellationToken()
    token.cancel()
    client, recorder, _ = make(ok(), cancel=token)
    with pytest.raises(CancellationError):
        client.fetch_bytes(URL)
    assert recorder.requests == []


def test_cancelling_while_waiting_to_retry_stops_at_once() -> None:
    token = CancellationToken()

    def handler(_request: httpx.Request) -> httpx.Response:
        token.cancel()
        return httpx.Response(503)

    client, recorder, _ = make(handler, cancel=token, retries=5)
    with pytest.raises(CancellationError):
        client.fetch_bytes(URL)
    assert len(recorder.requests) == 1
