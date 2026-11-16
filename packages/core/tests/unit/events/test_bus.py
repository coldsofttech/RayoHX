import logging

import pytest

from rayohx import DownloadState, EventType
from rayohx.events import DownloadEvent, EventBus


def _event(kind: EventType = EventType.DOWNLOAD_STARTED) -> DownloadEvent:
    return DownloadEvent(type=kind, download_id="d1", state=DownloadState.QUEUED)


def test_bus_delivers_in_order_and_unsubscribes() -> None:
    bus = EventBus()
    seen: list[str] = []
    stop_first = bus.subscribe(lambda event: seen.append(f"a:{event.type.value}"))
    bus.subscribe(lambda event: seen.append(f"b:{event.type.value}"))
    bus.emit(_event())
    stop_first()
    stop_first()
    bus.emit(_event(EventType.DOWNLOAD_COMPLETED))
    assert seen == ["a:download_started", "b:download_started", "b:download_completed"]


def test_failing_listener_does_not_stop_others(caplog: pytest.LogCaptureFixture) -> None:
    bus = EventBus()
    seen: list[EventType] = []

    def broken(_event: DownloadEvent) -> None:
        raise RuntimeError("boom")

    bus.subscribe(broken)
    bus.subscribe(lambda event: seen.append(event.type))
    with caplog.at_level(logging.ERROR, logger="rayohx"):
        bus.emit(_event())
    assert seen == [EventType.DOWNLOAD_STARTED]
    assert "listener failed" in caplog.text
