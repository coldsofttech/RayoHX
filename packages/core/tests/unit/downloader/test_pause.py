"""Pausing and resuming a download."""

import threading
from pathlib import Path

import httpx

from rayohx import DownloadState, EventType
from rayohx.config import DownloadConfig, NetworkConfig
from rayohx.downloader import Downloader
from rayohx.events import DownloadEvent
from tests.helpers.media import BASE, Origin

CONFIG = DownloadConfig(network=NetworkConfig(retries=0, backoff_factor=0.001), concurrency=1)


def make(tmp_path: Path, count: int = 8) -> tuple[Origin, Downloader]:
    origin = Origin(count, content="ts")
    downloader = Downloader(
        BASE + "index.m3u8",
        output=tmp_path / "out.ts",
        config=CONFIG,
        transport=httpx.MockTransport(origin),
    )
    return origin, downloader


def test_no_segment_starts_while_paused_and_the_file_is_still_correct(tmp_path: Path) -> None:
    origin, downloader = make(tmp_path)
    log: list[str] = []
    resumed = threading.Event()

    def listen(event: DownloadEvent) -> None:
        if event.type is EventType.SEGMENT_STARTED:
            log.append("started")
        elif event.type in {EventType.DOWNLOAD_PAUSED, EventType.DOWNLOAD_RESUMED}:
            log.append(event.type.value)
        elif event.type is EventType.SEGMENT_COMPLETED and "download_paused" not in log:
            downloader.pause()
            assert downloader.is_paused
            threading.Timer(0.3, downloader.resume).start()
        if event.type is EventType.DOWNLOAD_RESUMED:
            resumed.set()

    downloader.events.subscribe(listen)
    result = downloader.run()
    assert result.state is DownloadState.COMPLETED
    assert resumed.wait(1)
    assert (tmp_path / "out.ts").read_bytes() == origin.expected()
    paused_at = log.index("download_paused")
    resumed_at = log.index("download_resumed")
    # Anything between the two events was already running when the pause was asked for.
    assert "started" not in log[paused_at + 1 : resumed_at]
    assert "started" in log[resumed_at:]
    assert not downloader.is_paused


def test_events_from_segments_still_running_report_paused(tmp_path: Path) -> None:
    origin = Origin(10, content="ts")
    config = DownloadConfig(network=NetworkConfig(retries=0), concurrency=4)
    downloader = Downloader(
        BASE + "index.m3u8",
        output=tmp_path / "out.ts",
        config=config,
        transport=httpx.MockTransport(origin),
    )
    paused: list[DownloadEvent] = []
    seen_pause = threading.Event()

    def listen(event: DownloadEvent) -> None:
        if event.type is EventType.DOWNLOAD_PAUSED:
            seen_pause.set()
        elif event.type is EventType.DOWNLOAD_RESUMED:
            seen_pause.clear()
        elif seen_pause.is_set():
            paused.append(event)
        elif event.type is EventType.SEGMENT_COMPLETED and not downloader.is_paused:
            downloader.pause()
            threading.Timer(0.3, downloader.resume).start()

    downloader.events.subscribe(listen)
    assert downloader.run().success
    running = {EventType.SEGMENT_STARTED, EventType.SEGMENT_COMPLETED, EventType.DOWNLOAD_PROGRESS}
    reports = [event for event in paused if event.type in running]
    assert reports
    assert {event.state for event in reports} == {DownloadState.PAUSED}


def test_a_pause_before_the_download_waits_for_resume(tmp_path: Path) -> None:
    origin, downloader = make(tmp_path, count=3)
    downloader.pause()
    timer = threading.Timer(0.3, downloader.resume)
    timer.start()
    result = downloader.run()
    timer.join()
    assert result.success
    assert (tmp_path / "out.ts").read_bytes() == origin.expected()


def test_cancelling_a_paused_download_stops_it(tmp_path: Path) -> None:
    _origin, downloader = make(tmp_path)

    def listen(event: DownloadEvent) -> None:
        if event.type is EventType.DOWNLOAD_PAUSED:
            threading.Timer(0.2, downloader.cancel).start()
        elif event.type is EventType.SEGMENT_COMPLETED and not downloader.is_paused:
            downloader.pause()

    downloader.events.subscribe(listen)
    result = downloader.run()
    assert result.state is DownloadState.CANCELLED


def test_resume_without_a_pause_does_nothing(tmp_path: Path) -> None:
    _origin, downloader = make(tmp_path, count=2)
    downloader.resume()
    assert downloader.run().success
