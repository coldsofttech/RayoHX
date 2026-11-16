import gzip

import httpx
import pytest

from rayohx import CancellationToken
from rayohx.errors import (
    CancellationError,
    ConfigurationError,
    HTTPError,
    NetworkTimeoutError,
)
from tests.helpers.http import URL, Body, FakeTime, Handler, make, ok, sequence


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


def test_custom_user_agent_and_headers_are_sent() -> None:
    client, recorder, _ = make(
        ok(), user_agent="Agent/2", headers={"Referer": "https://site.example/", "X-Extra": "1"}
    )
    client.fetch_bytes(URL)
    headers = recorder.requests[0].headers
    assert headers["user-agent"] == "Agent/2"
    assert headers["referer"] == "https://site.example/"
    assert headers["x-extra"] == "1"


def test_a_user_agent_header_replaces_the_default() -> None:
    client, recorder, _ = make(ok(), headers={"user-agent": "Mine"})
    client.fetch_bytes(URL)
    assert recorder.requests[0].headers.get_list("user-agent") == ["Mine"]


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


SECRETS = {"Authorization": "Bearer s3", "X-Api-Key": "k3", "Referer": "https://site.example/"}


def echo_after_redirect() -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "media.example.com":
            return httpx.Response(302, headers={"location": "https://cdn.other.net/seg.ts"})
        return httpx.Response(200, content=b"segment")

    return handler


def test_secrets_do_not_follow_a_redirect_to_another_host() -> None:
    client, recorder, _ = make(echo_after_redirect(), headers=SECRETS, cookies={"sid": "abc"})
    client.fetch_bytes(URL)
    first, second = recorder.requests
    assert first.headers["authorization"] == "Bearer s3"
    assert first.headers["x-api-key"] == "k3"
    assert first.headers["cookie"] == "sid=abc"
    for name in ("authorization", "x-api-key", "cookie"):
        assert name not in second.headers
    assert second.headers["referer"] == "https://site.example/"
    assert second.headers["user-agent"] == "RayoHX"


def test_listed_credential_hosts_receive_secrets() -> None:
    client, recorder, _ = make(
        echo_after_redirect(),
        headers=SECRETS,
        cookies={"sid": "abc"},
        credential_hosts=("CDN.other.net",),
    )
    client.fetch_bytes(URL)
    second = recorder.requests[1]
    assert second.headers["authorization"] == "Bearer s3"
    assert second.headers["cookie"] == "sid=abc"


def test_a_fixed_origin_does_not_trust_a_different_first_host() -> None:
    client, recorder, _ = make(
        ok(), origin="https://start.example.com/m.m3u8", headers=SECRETS, cookies={"a": "b"}
    )
    client.fetch_bytes("https://elsewhere.example.org/a.ts")
    assert "authorization" not in recorder.requests[0].headers
    assert "cookie" not in recorder.requests[0].headers


def test_without_an_origin_the_first_host_is_trusted() -> None:
    client, recorder, _ = make(ok(), origin=None, headers=SECRETS)
    client.fetch_bytes("https://first.example.com/a.ts")
    client.fetch_bytes("https://second.example.com/a.ts")
    assert "authorization" in recorder.requests[0].headers
    assert "authorization" not in recorder.requests[1].headers


def test_an_explicit_cookie_header_is_not_duplicated() -> None:
    client, recorder, _ = make(ok(), headers={"Cookie": "mine=1"}, cookies={"sid": "abc"})
    client.fetch_bytes(URL)
    assert recorder.requests[0].headers.get_list("cookie") == ["mine=1"]


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


def test_progress_is_reported_per_chunk() -> None:
    body = b"x" * 200_000
    seen: list[int] = []
    client, _, _ = make(ok(body))
    client.fetch_bytes(URL, on_bytes=seen.append)
    assert sum(seen) == 200_000
    assert len(seen) > 1


def test_a_failure_part_way_through_a_body_is_retried_from_the_start() -> None:
    broken = httpx.Response(200, stream=Body([b"abc"], httpx.ReadError("reset")))
    client, recorder, _ = make(sequence(broken, httpx.Response(200, content=b"whole")))
    assert client.fetch_bytes(URL).content == b"whole"
    assert len(recorder.requests) == 2


def test_a_retry_that_would_pass_the_overall_limit_is_not_attempted() -> None:
    client, recorder, fake = make(
        lambda _r: httpx.Response(503), total_timeout=5, backoff_factor=10, retries=3
    )
    with pytest.raises(HTTPError):
        client.fetch_bytes(URL)
    assert len(recorder.requests) == 1
    assert fake.sleeps == []


def test_the_overall_limit_stops_a_slow_body() -> None:
    fake = FakeTime()
    client, recorder, _ = make(ok(b"x" * 200_000), fake=fake, total_timeout=5, retries=3)

    def slow(_size: int) -> None:
        fake.now += 10

    with pytest.raises(NetworkTimeoutError, match="overall") as info:
        client.fetch_bytes(URL, on_bytes=slow)
    assert not info.value.retryable
    assert len(recorder.requests) == 1


def test_downloads_respect_the_speed_limit() -> None:
    client, _, fake = make(ok(b"x" * 3000), rate_limit=1000)
    client.fetch_bytes(URL)
    assert fake.sleeps == [2.0]


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


def test_cancelling_while_reading_stops_between_chunks() -> None:
    token = CancellationToken()
    client, _, _ = make(ok(b"x" * 300_000), cancel=token)
    received: list[int] = []

    def on_bytes(size: int) -> None:
        received.append(size)
        token.cancel()

    with pytest.raises(CancellationError):
        client.fetch_bytes(URL, on_bytes=on_bytes)
    assert len(received) == 1
