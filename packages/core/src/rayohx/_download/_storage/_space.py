"""How much space a download needs, and whether the disk has it."""

import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from rayohx._download._storage._common import DEFAULT_SPILL_BYTES
from rayohx.config import StorageConfig
from rayohx.enums import StorageStrategy
from rayohx.errors import InsufficientStorageError
from rayohx.models import MediaPlaylist, Variant

#: Allowance for container overhead on top of the stream's own bitrate.
ESTIMATE_MARGIN = 1.05


class SizeEstimator:
    """Estimates the total download size without asking the server for every segment.

    It starts from the stream's bitrate and duration, then switches to the sizes actually seen,
    so the figure improves as the download goes on.
    """

    def __init__(self, durations: list[float], bits_per_second: int | None) -> None:
        self._total_duration = sum(durations)
        self._count = len(durations)
        self._initial_rate = bits_per_second / 8 if bits_per_second else None
        self._seen_bytes = 0
        self._seen_duration = 0.0
        self._seen_count = 0
        self._lock = threading.Lock()

    @classmethod
    def for_playlist(cls, playlist: MediaPlaylist, variant: Variant | None) -> "SizeEstimator":
        """Build an estimator from a playlist and, when known, the variant it belongs to."""
        rate = None
        if variant is not None:
            rate = variant.average_bandwidth or variant.bandwidth
        return cls([segment.duration for segment in playlist.segments], rate)

    @property
    def samples(self) -> int:
        """How many segments have been measured."""
        return self._seen_count

    def observe(self, duration: float, size: int) -> None:
        """Record the real size of a finished segment."""
        with self._lock:
            self._seen_bytes += size
            self._seen_duration += duration
            self._seen_count += 1

    def bytes_per_second(self) -> float | None:
        """The best known data rate."""
        with self._lock:
            if self._seen_duration > 0:
                return self._seen_bytes / self._seen_duration
            return self._initial_rate

    def total_bytes(self) -> int | None:
        """Estimated size of the whole download, or ``None`` if nothing is known yet."""
        rate = self.bytes_per_second()
        if rate is None:
            return None
        return int(rate * self._total_duration)

    def average_segment_bytes(self) -> int:
        """Typical size of one segment, or 0 if unknown."""
        with self._lock:
            if self._seen_count:
                return self._seen_bytes // self._seen_count
        total = self.total_bytes()
        return total // self._count if total and self._count else 0


@dataclass(frozen=True, slots=True)
class SpaceNeed:
    """Disk space a strategy needs, split by where it goes."""

    output_bytes: int
    workspace_bytes: int


def space_needed(
    strategy: StorageStrategy, estimate: int, config: StorageConfig, *, writes_file: bool = True
) -> SpaceNeed:
    """What ``strategy`` needs for a download of about ``estimate`` bytes.

    The old rule of "twice the output" is wrong for most strategies: a direct or streaming
    download needs the output only, and a hybrid one needs a bounded amount of working space.
    """
    estimate = int(estimate * ESTIMATE_MARGIN)
    output = estimate if writes_file else 0
    limit = config.max_temp_bytes
    if strategy is StorageStrategy.TEMPORARY:
        workspace = min(estimate, limit) if limit else estimate
    elif strategy is StorageStrategy.HYBRID:
        workspace = min(estimate, limit or DEFAULT_SPILL_BYTES)
    else:
        workspace = 0
    return SpaceNeed(output_bytes=output, workspace_bytes=workspace)


def nearest_existing(path: Path) -> Path:
    """The closest parent of ``path`` that exists, so free space can be read before creating it."""
    current = Path(path).absolute()
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def free_bytes(path: Path) -> int:
    """Free space on the disk holding ``path``."""
    return shutil.disk_usage(nearest_existing(path)).free


def same_volume(first: Path, second: Path) -> bool:
    """Whether two paths are on the same disk."""
    a, b = nearest_existing(first), nearest_existing(second)
    try:
        dev_a, dev_b = a.stat().st_dev, b.stat().st_dev
    except OSError:
        return a.anchor == b.anchor
    if dev_a and dev_b:  # Windows reports 0 on older Python versions
        return dev_a == dev_b
    return a.anchor == b.anchor


def check_disk_space(
    need: SpaceNeed,
    *,
    output_dir: Path,
    workspace_dir: Path,
    reserve_bytes: int,
    free: Callable[[Path], int] = free_bytes,
) -> None:
    """Make sure the disk(s) can hold ``need`` plus ``reserve_bytes``.

    When the output and the working folder share a disk their needs add up; otherwise each disk is
    checked on its own.

    Raises:
        InsufficientStorageError: If there is not enough space.
    """
    if same_volume(output_dir, workspace_dir):
        _require(need.output_bytes + need.workspace_bytes + reserve_bytes, output_dir, free)
        return
    if need.output_bytes:
        _require(need.output_bytes + reserve_bytes, output_dir, free)
    if need.workspace_bytes:
        _require(need.workspace_bytes + reserve_bytes, workspace_dir, free)


def _require(required: int, location: Path, free: Callable[[Path], int]) -> None:
    available = free(location)
    if required > available:
        raise InsufficientStorageError(required, available, location=str(location))
