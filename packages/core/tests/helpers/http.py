from collections.abc import Callable, Iterator

import httpx

from rayohx import CancellationToken
from rayohx._http import HttpClient
from rayohx.config import NetworkConfig

ORIGIN = "https://media.example.com/vod/master.m3u8"


Handler = Callable[[httpx.Request], httpx.Response]


class FakeTime:
    """A clock that only moves when something sleeps or the test moves it."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class Body(httpx.SyncByteStream):
    """A response body that can fail part-way."""

    def __init__(self, chunks: list[bytes], error: Exception | None = None) -> None:
        self.chunks = chunks
        self.error = error

    def __iter__(self) -> Iterator[bytes]:
        yield from self.chunks
        if self.error is not None:
            raise self.error


class Recorder:
    """Wraps a handler and remembers every request it saw."""

    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def make(
    handler: Handler,
    *,
    fake: FakeTime | None = None,
    origin: str | None = ORIGIN,
    cancel: CancellationToken | None = None,
    url_guard: Callable[[str], None] | None = None,
    **network: object,
) -> tuple[HttpClient, Recorder, FakeTime]:
    fake = fake or FakeTime()
    recorder = Recorder(handler)
    client = HttpClient(
        NetworkConfig(**network),  # type: ignore[arg-type]
        origin_url=origin,
        cancel=cancel,
        url_guard=url_guard,
        transport=httpx.MockTransport(recorder),
        sleep=fake.sleep,
        clock=fake.clock,
    )
    return client, recorder, fake


def ok(content: bytes = b"data", **headers: str) -> Handler:
    return lambda _request: httpx.Response(200, content=content, headers=headers)


def sequence(*responses: httpx.Response) -> Handler:
    queue = list(responses)
    return lambda _request: queue.pop(0) if len(queue) > 1 else queue[0]


URL = "https://media.example.com/vod/a.ts"
