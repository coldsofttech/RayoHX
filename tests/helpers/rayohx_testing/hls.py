"""A small VOD stream, served by ``LocalServer``: ``/index.m3u8`` and ``/seg<N>.ts``."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import threading

    from rayohx_testing.servers import Route, Seen

PACKETS = 10


def media_playlist(count: int) -> str:
    lines = ["#EXTM3U", "#EXT-X-TARGETDURATION:4", "#EXT-X-PLAYLIST-TYPE:VOD"]
    for index in range(count):
        lines += ["#EXTINF:4.0,", f"seg{index}.ts"]
    return "\n".join([*lines, "#EXT-X-ENDLIST"]) + "\n"


def segment_data(index: int) -> bytes:
    from rayohx_testing.media import ts_payload

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

    from rayohx_testing.servers import Reply

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
