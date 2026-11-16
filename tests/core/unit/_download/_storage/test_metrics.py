from rayohx._download._storage import (
    StorageTracker,
)


def test_the_tracker_follows_usage_and_remembers_the_peak() -> None:
    tracker = StorageTracker()
    tracker.downloaded(500)
    tracker.written(400)
    tracker.memory(300)
    tracker.disk(200)
    tracker.disk(300)
    tracker.disk(-450)
    snapshot = tracker.snapshot()
    assert snapshot.downloaded_bytes == 500
    assert snapshot.written_bytes == snapshot.output_bytes == 400
    assert snapshot.temporary_bytes == 50
    assert snapshot.peak_temporary_bytes == 500
    assert snapshot.working_bytes == 350
    assert (tracker.memory_bytes, tracker.disk_bytes) == (300, 50)
