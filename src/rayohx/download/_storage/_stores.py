"""Where finished segments wait for their turn."""

import os
import shutil
import struct
import threading
from pathlib import Path
from typing import Protocol

from rayohx.config import StorageConfig
from rayohx.download._storage._common import translate_os_error
from rayohx.download._storage._metrics import StorageTracker
from rayohx.enums import StorageStrategy
from rayohx.models import SegmentData

_HEADER = struct.Struct(">Q")


class SegmentStore(Protocol):
    """Holds segments that finished before their turn to be written."""

    def put(self, data: SegmentData) -> None: ...

    def has(self, index: int) -> bool: ...

    def take(self, index: int) -> SegmentData: ...

    def existing(self) -> set[int]:
        """Indexes already present before the download started (left by an earlier run)."""
        ...

    def clear(self) -> None: ...


class MemoryStore:
    """Keeps segments in memory."""

    def __init__(self, tracker: StorageTracker) -> None:
        self._items: dict[int, SegmentData] = {}
        self._tracker = tracker
        self._lock = threading.Lock()

    def put(self, data: SegmentData) -> None:
        with self._lock:
            self._items[data.index] = data
        self._tracker.memory(data.size)

    def has(self, index: int) -> bool:
        with self._lock:
            return index in self._items

    def take(self, index: int) -> SegmentData:
        with self._lock:
            data = self._items.pop(index)
        self._tracker.memory(-data.size)
        return data

    def existing(self) -> set[int]:
        return set()

    def clear(self) -> None:
        with self._lock:
            freed = sum(item.size for item in self._items.values())
            self._items.clear()
        self._tracker.memory(-freed)


class DiskStore:
    """Keeps segments as files in a folder. A file appears only once it is completely written."""

    def __init__(self, folder: Path, tracker: StorageTracker) -> None:
        self._folder = folder
        self._tracker = tracker
        self._sizes: dict[int, int] = {}
        self._lock = threading.Lock()
        self._folder.mkdir(parents=True, exist_ok=True)
        self._found = self._scan()

    def _path(self, index: int) -> Path:
        return self._folder / f"{index:08d}.seg"

    def _scan(self) -> set[int]:
        """Find complete files from an earlier run and count them as temporary storage."""
        found: set[int] = set()
        if not self._folder.is_dir():
            return found
        for path in self._folder.iterdir():
            if path.suffix == ".tmp":
                path.unlink(missing_ok=True)  # a write that never finished
            elif path.suffix == ".seg" and path.stem.isdigit() and self._valid(path):
                index = int(path.stem)
                size = path.stat().st_size
                self._sizes[index] = size
                self._tracker.disk(size)
                found.add(index)
            elif path.suffix == ".seg":
                path.unlink(missing_ok=True)
        return found

    @staticmethod
    def _valid(path: Path) -> bool:
        try:
            size = path.stat().st_size
            if size < _HEADER.size:
                return False
            with path.open("rb") as handle:
                init_length: int = _HEADER.unpack(handle.read(_HEADER.size))[0]
            return bool(_HEADER.size + init_length <= size)
        except OSError:
            return False

    def put(self, data: SegmentData) -> None:
        final = self._path(data.index)
        temporary = final.with_suffix(".tmp")
        try:
            with temporary.open("wb") as handle:
                handle.write(_HEADER.pack(len(data.init)))
                handle.write(data.init)
                handle.write(data.media)
            os.replace(temporary, final)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise translate_os_error(exc, str(final)) from exc
        size = _HEADER.size + data.size
        with self._lock:
            self._sizes[data.index] = size
        self._tracker.disk(size)

    def has(self, index: int) -> bool:
        with self._lock:
            return index in self._sizes

    def take(self, index: int) -> SegmentData:
        path = self._path(index)
        raw = path.read_bytes()
        init_length: int = _HEADER.unpack_from(raw)[0]
        start = _HEADER.size
        data = SegmentData(
            index=index,
            init=raw[start : start + init_length],
            media=raw[start + init_length :],
        )
        path.unlink(missing_ok=True)
        with self._lock:
            size = self._sizes.pop(index, 0)
        self._tracker.disk(-size)
        return data

    def existing(self) -> set[int]:
        return set(self._found)

    def clear(self) -> None:
        with self._lock:
            freed = sum(self._sizes.values())
            self._sizes.clear()
        shutil.rmtree(self._folder, ignore_errors=True)
        self._tracker.disk(-freed)


class SpillStore:
    """Memory first, and files once ``memory_limit`` bytes are held."""

    def __init__(self, disk: DiskStore, tracker: StorageTracker, memory_limit: int) -> None:
        self._memory = MemoryStore(tracker)
        self._disk = disk
        self._tracker = tracker
        self._limit = memory_limit

    def put(self, data: SegmentData) -> None:
        if self._tracker.memory_bytes + data.size <= self._limit:
            self._memory.put(data)
        else:
            self._disk.put(data)

    def has(self, index: int) -> bool:
        return self._memory.has(index) or self._disk.has(index)

    def take(self, index: int) -> SegmentData:
        return self._memory.take(index) if self._memory.has(index) else self._disk.take(index)

    def existing(self) -> set[int]:
        return self._disk.existing()

    def clear(self) -> None:
        self._memory.clear()
        self._disk.clear()


def make_store(
    strategy: StorageStrategy,
    config: StorageConfig,
    tracker: StorageTracker,
    segments_dir: Path,
) -> SegmentStore:
    """Build the store a strategy uses."""
    if strategy is StorageStrategy.TEMPORARY:
        return DiskStore(segments_dir, tracker)
    if strategy is StorageStrategy.HYBRID:
        return SpillStore(DiskStore(segments_dir, tracker), tracker, config.buffer_bytes)
    return MemoryStore(tracker)
