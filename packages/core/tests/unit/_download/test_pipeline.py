"""The segment pipeline on its own: ordering, limits, failures, cancelling, events
and checkpoints.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from rayohx import CancellationToken, DownloadState, EventType, SegmentData
from rayohx._download._pipeline import SegmentPipeline
from rayohx._download._progress import ProgressTracker
from rayohx._download._storage import MemoryStore, SizeEstimator, StorageTracker
from rayohx.config import StorageConfig
from rayohx.errors import CancellationError, SegmentDownloadError
from rayohx.events import DownloadEvent, EventBus
from rayohx.models import Segment
from tests.helpers.storage import S, seg

SIZE = 10


class FakeFetcher:
    """Hands out segments of ``SIZE`` bytes, with optional delays, hooks and one failure."""

    def __init__(self) -> None:
        self.delays: dict[int, float] = {}
        self.hooks: dict[int, Callable[[], None]] = {}
        self.fail_at: int | None = None
        self.requested: list[int] = []
        self.max_active = 0
        self._active = 0
        self._lock = threading.Lock()

    def fetch(self, index: int, on_bytes: Callable[[int], None] | None = None) -> SegmentData:
        with self._lock:
            self.requested.append(index)
            self._active += 1
            self.max_active = max(self.max_active, self._active)
        try:
            time.sleep(self.delays.get(index, 0.0))
            if index in self.hooks:
                self.hooks[index]()
            if index == self.fail_at:
                raise SegmentDownloadError(index, f"https://example.com/{index}.ts", "boom")
            data = seg(index, SIZE)
            if on_bytes is not None:
                on_bytes(data.size)
            return data
        finally:
            with self._lock:
                self._active -= 1


class RecordingSink:
    """An output that only remembers what it was given, and in which order."""

    supports_resume = True
    writes_file = False
    target: Path | None = None

    def __init__(self) -> None:
        self.written: list[int] = []
        self.total = 0

    def preflight(self) -> None:
        return None

    def open(self, *, resume_offset: int | None = None) -> int:
        return 0

    def write(self, data: SegmentData) -> int:
        self.written.append(data.index)
        self.total += data.size
        return data.size

    def checkpoint(self) -> int:
        return self.total

    def commit(self, validate: object = None) -> None:
        return None

    def abort(self, *, keep_partial: bool) -> None:
        return None


@dataclass
class Rig:
    pipeline: SegmentPipeline
    fetcher: FakeFetcher
    sink: RecordingSink
    tracker: StorageTracker
    progress: ProgressTracker
    events: list[DownloadEvent]


def build(
    count: int,
    *,
    concurrency: int = 4,
    store: MemoryStore | None = None,
    cancel: CancellationToken | None = None,
    start_index: int = 0,
    on_checkpoint: Callable[[int, int], None] | None = None,
    recheck_space: Callable[[], None] | None = None,
) -> Rig:
    segments = [
        Segment(index=i, uri=f"https://example.com/{i}.ts", duration=2.0, sequence_number=i)
        for i in range(count)
    ]

    def clock() -> float:
        return 0.0  # a frozen clock keeps the time-based checkpoints out

    tracker = StorageTracker()
    estimator = SizeEstimator([2.0] * count, None)
    progress = ProgressTracker(count, estimator, tracker, clock=clock)
    config = StorageConfig()
    fetcher = FakeFetcher()
    sink = RecordingSink()
    bus = EventBus()
    events: list[DownloadEvent] = []
    bus.subscribe(events.append)
    pipeline = SegmentPipeline(
        segments=segments,
        fetcher=fetcher,  # type: ignore[arg-type]
        store=store or MemoryStore(tracker),
        sink=sink,
        strategy=S.DIRECT,
        concurrency=concurrency,
        storage=config,
        tracker=tracker,
        progress=progress,
        estimator=estimator,
        cancel=cancel,
        bus=bus,
        download_id="abc123",
        start_index=start_index,
        on_checkpoint=on_checkpoint,
        recheck_space=recheck_space,
        clock=clock,
    )
    return Rig(pipeline, fetcher, sink, tracker, progress, events)


def events_of(rig: Rig, kind: EventType) -> list[DownloadEvent]:
    return [event for event in rig.events if event.type is kind]


def test_segments_finishing_out_of_order_are_written_in_order() -> None:
    rig = build(12)
    rig.fetcher.delays = {index: (11 - index) * 0.002 for index in range(12)}
    rig.pipeline.run()
    assert rig.sink.written == list(range(12))
    assert rig.pipeline.head == 12
    assert rig.tracker.snapshot().written_bytes == 12 * SIZE


def test_no_more_segments_are_fetched_at_once_than_there_are_workers() -> None:
    rig = build(12, concurrency=3)
    rig.fetcher.delays = dict.fromkeys(range(12), 0.01)
    rig.pipeline.run()
    assert rig.fetcher.max_active <= 3
    assert rig.sink.written == list(range(12))


def test_one_worker_fetches_one_segment_after_another() -> None:
    rig = build(6, concurrency=1)
    rig.fetcher.delays = dict.fromkeys(range(6), 0.002)
    rig.pipeline.run()
    assert rig.fetcher.max_active == 1
    assert rig.fetcher.requested == list(range(6))


def test_a_slow_first_segment_holds_back_the_workers_beyond_the_window() -> None:
    rig = build(10, concurrency=2)  # the window is two segments per worker past the one due
    seen: set[int] = set()

    def hold_first() -> None:
        deadline = time.monotonic() + 2
        while len(rig.fetcher.requested) < 4 and time.monotonic() < deadline:
            time.sleep(0.005)
        time.sleep(0.05)  # long enough for a segment past the window to be started by mistake
        seen.update(rig.fetcher.requested)

    rig.fetcher.hooks[0] = hold_first
    rig.pipeline.run()
    assert seen == {0, 1, 2, 3}
    assert rig.sink.written == list(range(10))


def test_a_download_can_start_part_way_through() -> None:
    rig = build(6, start_index=3)
    rig.pipeline.run()
    assert rig.fetcher.requested == [3, 4, 5]
    assert rig.sink.written == [3, 4, 5]
    assert rig.pipeline.head == 6


def test_segments_already_waiting_in_the_store_are_not_fetched_again() -> None:
    class Resumed(MemoryStore):
        def existing(self) -> set[int]:
            return {3, 4}

    tracker = StorageTracker()
    store = Resumed(tracker)
    store.put(seg(3, SIZE))
    store.put(seg(4, SIZE))
    rig = build(8, concurrency=4, store=store)
    rig.pipeline.run()
    assert sorted(rig.fetcher.requested) == [0, 1, 2, 5, 6, 7]
    assert rig.sink.written == list(range(8))
    reused = [e for e in events_of(rig, EventType.SEGMENT_COMPLETED) if e.message]
    assert [e.segment_index for e in reused] == [3, 4]
    assert all(e.message == "Reused from earlier run." for e in reused)


def test_a_failed_segment_stops_the_download_and_is_reported() -> None:
    rig = build(6, concurrency=1)
    rig.fetcher.fail_at = 2
    with pytest.raises(SegmentDownloadError):
        rig.pipeline.run()
    assert rig.sink.written == [0, 1]
    (failed,) = events_of(rig, EventType.SEGMENT_FAILED)
    assert failed.segment_index == 2
    assert failed.message is not None
    assert "Segment 2 failed" in failed.message


def test_cancelling_stops_the_download_with_a_cancellation_error() -> None:
    token = CancellationToken()
    rig = build(6, concurrency=1, cancel=token)
    rig.fetcher.hooks[1] = token.cancel
    with pytest.raises(CancellationError):
        rig.pipeline.run()
    assert rig.sink.written == [0]
    assert rig.fetcher.requested == [0, 1]


def test_progress_and_events_describe_a_finished_download() -> None:
    rig = build(5)
    rig.pipeline.run()
    assert {e.segment_index for e in events_of(rig, EventType.SEGMENT_STARTED)} == {0, 1, 2, 3, 4}
    assert len(events_of(rig, EventType.SEGMENT_COMPLETED)) == 5
    assert rig.events[-1].type is EventType.DOWNLOAD_PROGRESS
    assert all(e.download_id == "abc123" for e in rig.events)
    snapshot = rig.progress.snapshot(DownloadState.DOWNLOADING, 0)
    assert snapshot.completed_segments == 5
    assert snapshot.downloaded_bytes == 5 * SIZE


def test_a_checkpoint_is_taken_every_sixteen_segments() -> None:
    checkpoints: list[tuple[int, int]] = []
    rig = build(40, on_checkpoint=lambda head, durable: checkpoints.append((head, durable)))
    rig.pipeline.run()
    assert checkpoints == [(16, 16 * SIZE), (32, 32 * SIZE)]


def test_a_failure_still_saves_how_far_the_download_got() -> None:
    checkpoints: list[tuple[int, int]] = []
    rig = build(
        6, concurrency=1, on_checkpoint=lambda head, durable: checkpoints.append((head, durable))
    )
    rig.fetcher.fail_at = 2
    with pytest.raises(SegmentDownloadError):
        rig.pipeline.run()
    assert checkpoints[-1] == (2, 2 * SIZE)


def test_the_disk_space_is_checked_again_once_the_sizes_are_known() -> None:
    calls: list[int] = []
    rig = build(8, recheck_space=lambda: calls.append(1))
    rig.pipeline.run()
    assert calls == [1]
