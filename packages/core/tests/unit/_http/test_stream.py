"""Reading a response body: size, time and speed limits, integrity checks and cancellation."""

import httpx
import pytest

from rayohx import CancellationToken
from rayohx.errors import CancellationError, InvalidResponseError, NetworkTimeoutError
from rayohx.models import SegmentRange
from tests.helpers.http import URL, Body, FakeTime, make, ok, sequence


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


def test_a_web_page_served_as_media_is_refused_and_retried() -> None:
    page = httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})
    client, recorder, _ = make(sequence(page, httpx.Response(200, content=b"ts")), retries=1)
    assert client.fetch_bytes(URL).content == b"ts"
    assert len(recorder.requests) == 2


def test_a_body_over_the_limit_is_refused() -> None:
    client, _, _ = make(ok(b"x" * 100), retries=0)
    with pytest.raises(InvalidResponseError, match="larger than"):
        client.fetch_bytes(URL, max_bytes=10)


def test_a_body_shorter_than_declared_is_refused() -> None:
    cut = httpx.Response(200, stream=Body([b"abc"]), headers={"content-length": "10"})
    client, _, _ = make(sequence(cut), retries=0)
    with pytest.raises(InvalidResponseError, match="cut short"):
        client.fetch_bytes(URL)


def test_an_empty_body_is_refused() -> None:
    client, _, _ = make(ok(b""), retries=0)
    with pytest.raises(InvalidResponseError, match="empty"):
        client.fetch_bytes(URL)


def test_a_range_of_the_wrong_size_is_refused() -> None:
    partial = httpx.Response(206, content=b"abc", headers={"content-range": "bytes 0-4/100"})
    client, _, _ = make(sequence(partial), retries=0)
    with pytest.raises(InvalidResponseError):
        client.fetch_bytes(URL, byte_range=SegmentRange(offset=0, length=5))


def test_a_cancelled_token_stops_before_reading() -> None:
    token = CancellationToken()
    token.cancel()
    client, _, _ = make(ok(), cancel=token)
    with pytest.raises(CancellationError):
        client.fetch_bytes(URL)


def test_a_passed_deadline_stops_the_next_chunk() -> None:
    fake = FakeTime()
    client, _, _ = make(ok(b"x" * 200_000), fake=fake, total_timeout=1, retries=0)

    def advance(_size: int) -> None:
        fake.now += 10

    with pytest.raises(NetworkTimeoutError):
        client.fetch_bytes(URL, on_bytes=advance)
