"""The public ``Downloader`` run against a real local server: finish, pause, cancel and resume."""

import threading
import time
from pathlib import Path

import pytest
from rayohx_testing.hls import expected, segment_index, vod_routes
from rayohx_testing.servers import LocalServer

from rayohx import CancellationToken, Downloader, DownloadResult, DownloadState, EventType
from rayohx.config import DownloadConfig, OutputConfig
from rayohx.enums import OutputFormat

SEGMENT_DELAY = 0.25


def _segments(server: LocalServer) -> list[int]:
    found = (segment_index(seen) for seen in list(server.requests))
    return [index for index in found if index is not None]


def _downloader(url: str, output: Path, cancel: CancellationToken | None = None) -> Downloader:
    config = DownloadConfig(concurrency=1, output=OutputConfig(format=OutputFormat.TS))
    return Downloader(url, output=output, config=config, cancel=cancel)


def _run_in_thread(downloader: Downloader) -> tuple[threading.Thread, list[DownloadResult]]:
    results: list[DownloadResult] = []
    thread = threading.Thread(target=lambda: results.append(downloader.run()), daemon=True)
    thread.start()
    return thread, results


def _wait_for_segments(server: LocalServer, wanted: int) -> None:
    deadline = time.monotonic() + 30
    while len(set(_segments(server))) < wanted:
        assert time.monotonic() < deadline, "the download did not start"
        time.sleep(0.05)


def test_a_download_finishes_with_the_right_file(tmp_path: Path) -> None:
    out = tmp_path / "clip.ts"
    with LocalServer(vod_routes(8)) as server:
        downloader = _downloader(f"{server.url}/index.m3u8", out)
        kinds: list[EventType] = []
        downloader.events.subscribe(lambda event: kinds.append(event.type))
        result = downloader.run()
    assert result.state is DownloadState.COMPLETED
    assert result.output is not None
    assert result.output.size_bytes == len(expected(8))
    assert out.read_bytes() == expected(8)
    assert kinds[-1] is EventType.DOWNLOAD_COMPLETED
    assert sorted(path.name for path in tmp_path.iterdir()) == ["clip.ts"]


def test_pause_stops_new_segments_until_resume(tmp_path: Path) -> None:
    out = tmp_path / "clip.ts"
    count = 12
    with LocalServer(vod_routes(count, delay=SEGMENT_DELAY)) as server:
        downloader = _downloader(f"{server.url}/index.m3u8", out)
        thread, results = _run_in_thread(downloader)
        _wait_for_segments(server, 2)
        downloader.pause()
        assert downloader.is_paused
        time.sleep(0.8)  # the segment that was already being fetched finishes
        settled = len(_segments(server))
        time.sleep(1.0)
        assert len(_segments(server)) == settled < count
        downloader.resume()
        thread.join(timeout=30)
        assert not thread.is_alive()
        assert sorted(_segments(server)) == list(range(count))
    assert results[0].state is DownloadState.COMPLETED
    assert out.read_bytes() == expected(count)


def test_cancel_returns_a_cancelled_result_without_output(tmp_path: Path) -> None:
    out = tmp_path / "clip.ts"
    with LocalServer(vod_routes(20, delay=SEGMENT_DELAY)) as server:
        downloader = _downloader(f"{server.url}/index.m3u8", out)
        thread, results = _run_in_thread(downloader)
        _wait_for_segments(server, 2)
        downloader.cancel()
        thread.join(timeout=30)
        assert not thread.is_alive()
        assert len(set(_segments(server))) < 20
    assert results[0].state is DownloadState.CANCELLED
    assert not out.exists()


@pytest.mark.parametrize("count", [20])
def test_a_cancelled_download_resumes_where_it_stopped(tmp_path: Path, count: int) -> None:
    out = tmp_path / "clip.ts"
    with LocalServer(vod_routes(count, delay=SEGMENT_DELAY)) as server:
        url = f"{server.url}/index.m3u8"
        first = _downloader(url, out)
        thread, results = _run_in_thread(first)
        _wait_for_segments(server, 12)
        first.cancel()
        thread.join(timeout=30)
        assert results[0].state is DownloadState.CANCELLED
        server.requests.clear()
        second = _downloader(url, out).run()
        refetched = len(_segments(server))
    assert second.state is DownloadState.COMPLETED
    assert refetched < count
    assert out.read_bytes() == expected(count)
