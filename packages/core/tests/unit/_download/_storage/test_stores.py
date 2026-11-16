import errno
from pathlib import Path

import pytest

from rayohx._download._storage import (
    DiskStore,
    MemoryStore,
    SpillStore,
    StorageTracker,
    make_store,
)
from rayohx.config import StorageConfig
from rayohx.errors import InsufficientStorageError
from tests.helpers.storage import S, seg


def test_memory_store_holds_and_releases_segments() -> None:
    tracker = StorageTracker()
    store = MemoryStore(tracker)
    store.put(seg(3, 100))
    store.put(seg(1, 50, init=b"II"))
    assert store.has(3)
    assert not store.has(2)
    assert tracker.memory_bytes == 152
    taken = store.take(1)
    assert (taken.media, taken.init) == (bytes([1]) * 50, b"II")
    assert tracker.memory_bytes == 100
    assert store.existing() == set()
    store.clear()
    assert tracker.memory_bytes == 0
    assert not store.has(3)


def test_disk_store_round_trips_segments_and_frees_space(tmp_path: Path) -> None:
    tracker = StorageTracker()
    store = DiskStore(tmp_path / "segments", tracker)
    store.put(seg(2, 100, init=b"INIT"))
    store.put(seg(7, 10))
    assert store.has(2)
    assert tracker.disk_bytes == 8 + 104 + 8 + 10
    assert sorted(path.name for path in (tmp_path / "segments").iterdir()) == [
        "00000002.seg",
        "00000007.seg",
    ]
    taken = store.take(2)
    assert (taken.init, taken.media) == (b"INIT", bytes([2]) * 100)
    assert not store.has(2)
    assert tracker.disk_bytes == 18
    assert tracker.snapshot().peak_temporary_bytes == 130


def test_disk_store_finds_complete_files_from_an_earlier_run(tmp_path: Path) -> None:
    folder = tmp_path / "segments"
    first = DiskStore(folder, StorageTracker())
    first.put(seg(1, 100))
    first.put(seg(2, 100, init=b"X"))
    (folder / "00000003.tmp").write_bytes(b"half written")
    (folder / "00000004.seg").write_bytes(b"short")  # too short to be valid
    (folder / "00000005.seg").write_bytes((1000).to_bytes(8, "big") + b"abc")  # header lies
    (folder / "note.seg").write_bytes(b"?")

    tracker = StorageTracker()
    second = DiskStore(folder, tracker)
    assert second.existing() == {1, 2}
    assert second.has(1)
    assert tracker.disk_bytes == 108 + 109
    assert sorted(path.name for path in folder.iterdir()) == ["00000001.seg", "00000002.seg"]
    assert second.take(2).init == b"X"


def test_disk_store_clear_removes_everything(tmp_path: Path) -> None:
    tracker = StorageTracker()
    store = DiskStore(tmp_path / "segments", tracker)
    store.put(seg(1))
    store.clear()
    assert not (tmp_path / "segments").exists()
    assert tracker.disk_bytes == 0


def test_a_failed_write_leaves_no_partial_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = DiskStore(tmp_path / "segments", StorageTracker())

    def full(_source: object, _target: object) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr("rayohx._download._storage._stores.os.replace", full)
    with pytest.raises(InsufficientStorageError):
        store.put(seg(1))
    assert list((tmp_path / "segments").iterdir()) == []
    assert not store.has(1)


def test_spill_store_uses_memory_first_and_then_disk(tmp_path: Path) -> None:
    tracker = StorageTracker()
    store = SpillStore(DiskStore(tmp_path / "segments", tracker), tracker, memory_limit=250)
    for index in range(5):
        store.put(seg(index, 100))
    assert tracker.memory_bytes == 200
    assert tracker.disk_bytes == 3 * 108
    assert all(store.has(index) for index in range(5))
    assert store.take(0).index == 0  # from memory
    assert store.take(4).index == 4  # from disk
    assert tracker.memory_bytes == 100
    assert tracker.disk_bytes == 2 * 108
    store.clear()
    assert (tracker.memory_bytes, tracker.disk_bytes) == (0, 0)
    assert store.existing() == set()


def test_each_strategy_gets_the_right_store(tmp_path: Path) -> None:
    tracker = StorageTracker()
    config = StorageConfig()
    folder = tmp_path / "segments"
    assert isinstance(make_store(S.DIRECT, config, tracker, folder), MemoryStore)
    assert isinstance(make_store(S.STREAMING, config, tracker, folder), MemoryStore)
    assert isinstance(make_store(S.BUFFERED, config, tracker, folder), MemoryStore)
    assert isinstance(make_store(S.TEMPORARY, config, tracker, folder), DiskStore)
    assert isinstance(make_store(S.HYBRID, config, tracker, folder), SpillStore)
