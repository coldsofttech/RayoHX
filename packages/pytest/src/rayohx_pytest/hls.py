"""A small VOD stream, served by ``LocalServer``: ``/index.m3u8`` and ``/seg<N>.ts``."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from rayohx_pytest.fixtures import fixture_bytes
from rayohx_pytest.servers import LocalServer, Reply

if TYPE_CHECKING:
    from types import TracebackType

    from rayohx_pytest.servers import Route, Seen

PACKETS = 10


def media_playlist(count: int) -> str:
    lines = ["#EXTM3U", "#EXT-X-TARGETDURATION:4", "#EXT-X-PLAYLIST-TYPE:VOD"]
    for index in range(count):
        lines += ["#EXTINF:4.0,", f"seg{index}.ts"]
    return "\n".join([*lines, "#EXT-X-ENDLIST"]) + "\n"


def segment_data(index: int) -> bytes:
    from rayohx_pytest.media import ts_payload

    return ts_payload(index, PACKETS)


def expected(count: int) -> bytes:
    """What a finished download of ``count`` segments contains."""
    return b"".join(segment_data(index) for index in range(count))


def segment_index(seen: Seen) -> int | None:
    """Which segment a request asked for, or ``None`` for anything else."""
    name = seen.path.rsplit("/", 1)[-1]
    if name.startswith("seg") and name.endswith(".ts"):
        return int(name.removeprefix("seg").removesuffix(".ts"))
    return None


def vod_routes(
    count: int,
    *,
    delay: float = 0.0,
    gate: threading.Event | None = None,
    gate_from: int = 0,
) -> dict[str, Route]:
    """Routes for a ``count``-segment stream.

    ``delay`` slows each segment. With a ``gate``, segments from ``gate_from`` on wait until the
    event is set, so a test can hold a download open at a known point.
    """
    import time

    routes: dict[str, Route] = {}
    body = media_playlist(count).encode()
    routes["/index.m3u8"] = lambda _s: Reply(body=body)
    for index in range(count):

        def serve(_seen: Seen, index: int = index) -> Reply:
            if gate is not None and index >= gate_from:
                gate.wait(60)
            if delay:
                time.sleep(delay)
            return Reply(body=segment_data(index))

        routes[f"/seg{index}.ts"] = serve
    return routes


class HlsServer(LocalServer):
    """A ``LocalServer`` that serves ``/master.m3u8``, ``/index.m3u8`` and ``/seg<N>.ts``.

    ``delay`` slows every segment. Segments from ``gate_from`` on wait until ``release()`` is
    called, so a test can hold a download open at a known point.
    """

    def __init__(self, *, count: int = 6, delay: float = 0.0, gate_from: int | None = None) -> None:
        self.gate = threading.Event()
        routes = vod_routes(
            count,
            delay=delay,
            gate=self.gate if gate_from is not None else None,
            gate_from=gate_from or 0,
        )
        master = fixture_bytes("hls/master_two_variants.m3u8")
        routes["/master.m3u8"] = lambda _s: Reply(body=master)
        super().__init__(routes)

    @property
    def playlist_url(self) -> str:
        return f"{self.url}/index.m3u8"

    @property
    def master_url(self) -> str:
        return f"{self.url}/master.m3u8"

    @property
    def segment_requests(self) -> list[int]:
        """The segment numbers asked for so far, in order (repeats included)."""
        found = (segment_index(seen) for seen in list(self.requests))
        return [index for index in found if index is not None]

    @property
    def headers_seen(self) -> list[dict[str, str]]:
        return [seen.headers for seen in list(self.requests)]

    def release(self) -> None:
        self.gate.set()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()
        super().__exit__(exc_type, exc, traceback)
