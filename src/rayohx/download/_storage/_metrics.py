"""Counting what a download holds in memory and on disk."""

import threading

from rayohx.models import StorageMetrics


class StorageTracker:
    """Counts bytes moved and kept. Safe to update from many threads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._memory = 0
        self._disk = 0
        self._peak_disk = 0
        self._downloaded = 0
        self._written = 0

    def downloaded(self, size: int) -> None:
        """Bytes that came off the network."""
        with self._lock:
            self._downloaded += size

    def written(self, size: int) -> None:
        """Bytes written to the output."""
        with self._lock:
            self._written += size

    def memory(self, delta: int) -> None:
        """Bytes added to (or removed from) the in-memory buffer."""
        with self._lock:
            self._memory += delta

    def disk(self, delta: int) -> None:
        """Bytes added to (or removed from) temporary files."""
        with self._lock:
            self._disk += delta
            self._peak_disk = max(self._peak_disk, self._disk)

    @property
    def memory_bytes(self) -> int:
        """Bytes currently buffered in memory."""
        with self._lock:
            return self._memory

    @property
    def disk_bytes(self) -> int:
        """Bytes currently in temporary files."""
        with self._lock:
            return self._disk

    def snapshot(self) -> StorageMetrics:
        """The current figures."""
        with self._lock:
            return StorageMetrics(
                output_bytes=self._written,
                temporary_bytes=self._disk,
                working_bytes=self._disk + self._memory,
                peak_temporary_bytes=self._peak_disk,
                downloaded_bytes=self._downloaded,
                written_bytes=self._written,
            )
