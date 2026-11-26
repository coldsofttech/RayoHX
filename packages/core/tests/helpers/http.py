from collections.abc import Callable

import httpx
from rayohx_pytest.mocks import FakeTime, Handler, Recorder

from rayohx import CancellationToken
from rayohx._http import HttpClient
from rayohx.config import NetworkConfig

ORIGIN = "https://media.example.com/vod/master.m3u8"


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


URL = "https://media.example.com/vod/a.ts"
