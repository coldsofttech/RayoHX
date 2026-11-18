import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from rayohx.enums import DownloadState, EventType
from rayohx.events import DownloadEvent
from rayohx.platform.events import (
    EventBus,
    EventCategory,
    EventStore,
    PlatformEvent,
    Severity,
    from_download_event,
    sanitize,
)
from rayohx.platform.persistence import Database
from rayohx.redaction import REDACTED


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    with Database(tmp_path / "e.db") as database:
        yield database


def test_payload_secrets_never_survive() -> None:
    event = PlatformEvent(
        type="x",
        payload={
            "url": "https://u:pw@h.test/a.m3u8?token=abc&x=1",
            "headers": {"Authorization": "Bearer abc", "Accept": "*/*"},
            "password": "hunter2",
            "note": "cookie: sid=1",
            "nested": [{"api_key": "k"}],
        },
    )
    text = json.dumps(dict(event.payload))
    for secret in ("pw", "abc", "hunter2", "sid=1", '"k"'):
        assert secret not in text
    assert event.payload["password"] == REDACTED
    assert event.payload["headers"]["Accept"] == "*/*"


def test_payload_is_immutable_and_json_safe(tmp_path: Path) -> None:
    event = PlatformEvent(
        type="x",
        payload={
            "path": tmp_path,
            "state": DownloadState.FAILED,
            "n": float("nan"),
            "raw": b"1234",
        },
    )
    with pytest.raises(TypeError):
        event.payload["new"] = 1  # type: ignore[index]
    assert event.payload["path"] == str(tmp_path)
    assert event.payload["state"] == "failed"
    assert event.payload["n"] is None
    assert event.payload["raw"] == "<4 bytes>"
    json.dumps(dict(event.payload))


def test_sanitize_bounds_depth_and_length() -> None:
    deep: dict[str, Any] = {}
    cursor = deep
    for _ in range(20):
        cursor["a"] = {}
        cursor = cursor["a"]
    assert "..." in json.dumps(sanitize(deep))
    assert sanitize("x" * 10_000).endswith("...")
    assert len(sanitize("x" * 10_000)) < 4100


def test_to_dict_is_plain_data() -> None:
    event = PlatformEvent(
        type="queue.added", category=EventCategory.QUEUE, severity=Severity.WARNING, job_id="j"
    )
    data = event.to_dict()
    assert data["severity"] == "warning"
    assert data["category"] == "queue"
    json.dumps(data)


def test_store_assigns_ids_and_filters(db: Database) -> None:
    store = EventStore(db)
    a = store.append(PlatformEvent(type="a", job_id="j1", payload={"n": 1}))
    b = store.append(
        PlatformEvent(type="b", job_id="j2", category=EventCategory.QUEUE, severity=Severity.ERROR)
    )
    c = store.append(PlatformEvent(type="c", job_id="j1", severity=Severity.WARNING))
    assert (a.id, b.id, c.id) == (1, 2, 3)
    assert [e.type for e in store.query()] == ["a", "b", "c"]
    assert [e.type for e in store.query(newest_first=True)] == ["c", "b", "a"]
    assert [e.type for e in store.query(job_id="j1")] == ["a", "c"]
    assert [e.type for e in store.query(category=EventCategory.QUEUE)] == ["b"]
    assert [e.type for e in store.query(min_severity=Severity.WARNING)] == ["b", "c"]
    assert store.query(limit=1)[0].payload == {"n": 1}
    assert store.count() == 3
    assert store.count(job_id="j1") == 2
    assert store.last_id() == 3


def test_following_the_log_with_after_id_has_no_gaps(db: Database) -> None:
    store = EventStore(db)
    for i in range(5):
        store.append(PlatformEvent(type=f"e{i}"))
    seen = [e.id for e in store.query(limit=2)]
    seen += [e.id for e in store.query(after_id=seen[-1], limit=2)]
    seen += [e.id for e in store.query(after_id=seen[-1], limit=2)]
    assert seen == [1, 2, 3, 4, 5]
    assert store.query(after_id=5) == []


def test_prune_by_age_and_count(db: Database) -> None:
    store = EventStore(db)
    for i in range(10):
        store.append(PlatformEvent(type=f"e{i}", timestamp=float(i)))
    assert store.prune(older_than=3.0) == 3
    assert store.prune(keep_last=4) == 3
    assert [e.type for e in store.query()] == ["e6", "e7", "e8", "e9"]
    assert store.prune() == 0


def test_a_saved_event_survives_reopening(tmp_path: Path) -> None:
    path = tmp_path / "e.db"
    with Database(path) as database:
        EventStore(database).append(PlatformEvent(type="kept", job_id="j", payload={"a": [1, 2]}))
    with Database(path) as database:
        (event,) = EventStore(database).query()
        assert (event.type, event.job_id, dict(event.payload)) == ("kept", "j", {"a": [1, 2]})


def test_bus_saves_and_delivers(db: Database) -> None:
    store = EventStore(db)
    bus = EventBus(store)
    seen: list[PlatformEvent] = []
    unsubscribe = bus.subscribe(seen.append)
    delivered = bus.emit("queue.added", category=EventCategory.QUEUE, job_id="j", count=2)
    assert delivered.id == 1
    assert seen == [delivered]
    assert store.query()[0].payload == {"count": 2}
    unsubscribe()
    unsubscribe()
    bus.emit("queue.again")
    assert len(seen) == 1


def test_low_severity_events_are_delivered_but_not_saved(db: Database) -> None:
    store = EventStore(db)
    bus = EventBus(store)
    seen: list[PlatformEvent] = []
    bus.subscribe(seen.append)
    bus.emit("noise", severity=Severity.DEBUG)
    assert len(seen) == 1
    assert seen[0].id is None
    assert store.count() == 0


def test_a_failing_listener_or_store_never_stops_the_rest(db: Database) -> None:
    bus = EventBus(EventStore(db))
    seen: list[PlatformEvent] = []

    def bad(_: PlatformEvent) -> None:
        raise RuntimeError("boom")

    bus.subscribe(bad)
    bus.subscribe(seen.append)
    bus.emit("one")
    assert len(seen) == 1

    db.close()  # the store now fails; delivery must still happen
    bus.emit("two")
    assert [e.type for e in seen] == ["one", "two"]
    assert seen[1].id is None


def test_download_events_map_to_platform_events() -> None:
    failed = DownloadEvent(
        type=EventType.DOWNLOAD_FAILED,
        download_id="d1",
        state=DownloadState.FAILED,
        message="HTTP 403 for https://h.test/a?token=zzz",
    )
    event = from_download_event(failed, correlation_id="run-1")
    assert event.type == "download.failed"
    assert event.category is EventCategory.DOWNLOAD
    assert event.severity is Severity.ERROR
    assert event.job_id == "d1"
    assert event.correlation_id == "run-1"
    assert "zzz" not in json.dumps(dict(event.payload))

    segment = DownloadEvent(
        type=EventType.SEGMENT_COMPLETED,
        download_id="d1",
        state=DownloadState.DOWNLOADING,
        segment_index=4,
    )
    mapped = from_download_event(segment, job_id="job-9")
    assert mapped.severity is Severity.DEBUG
    assert mapped.job_id == "job-9"
    assert mapped.payload["segment"] == 4

    retry = DownloadEvent(
        type=EventType.SEGMENT_FAILED, download_id="d", state=DownloadState.DOWNLOADING
    )
    assert from_download_event(retry).severity is Severity.WARNING
    started = DownloadEvent(
        type=EventType.DOWNLOAD_STARTED, download_id="d", state=DownloadState.QUEUED
    )
    assert from_download_event(started).type == "download.started"


def test_bus_forward_saves_a_real_downloader_event_stream(db: Database) -> None:
    store = EventStore(db)
    bus = EventBus(store)
    bus.forward(
        DownloadEvent(type=EventType.DOWNLOAD_STARTED, download_id="d", state=DownloadState.QUEUED)
    )
    bus.forward(
        DownloadEvent(
            type=EventType.DOWNLOAD_PROGRESS, download_id="d", state=DownloadState.DOWNLOADING
        )
    )
    assert [e.type for e in store.query()] == ["download.started"]
