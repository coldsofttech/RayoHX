"""Watching free space while downloads run, and deciding what to do about it.

The guard is a small, pure decision-maker: the runner tells it how much room there is and what
is running, and it says whether a job may start and whether running jobs should wait or stop.
Doing the pausing and stopping is the runner's job.

* **Admission.** A job only starts if the room left, after what running downloads still have to
  write, stays above the pause threshold. A resumed or retried job brings its own estimate of how
  much it still needs; a new one is judged on room alone, and the engine checks its exact need
  once it has read the playlist.
* **Levels.** Below the warning threshold the guard reports; below the pause threshold it asks
  running jobs to wait; below the stop threshold it asks them to stop. Easing back needs a margin
  of extra room, so it does not flap around a threshold.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from rayohx.platform.storage.policy import StorageLevel, StoragePolicy
from rayohx.storage import disk_usage

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

#: The engine's own allowance for container overhead on top of the estimated size.
ESTIMATE_MARGIN = 1.05


def remaining_need(progress: Mapping[str, Any] | None) -> int:
    """How many more bytes a job still has to write, as far as its progress says."""
    if not progress:
        return 0
    total = progress.get("total_bytes")
    if not total:
        return 0
    return max(0, int(int(total) * ESTIMATE_MARGIN) - int(progress.get("written_bytes") or 0))


@dataclass(frozen=True, slots=True)
class GuardVerdict:
    """What a review of free space decided."""

    level: StorageLevel
    previous: StorageLevel
    free_bytes: int | None
    #: Running jobs that should wait for room.
    pause: tuple[str, ...] = ()
    #: Running jobs that should be stopped.
    stop: tuple[str, ...] = ()
    #: Whether jobs the guard paused may go on.
    resume: bool = False

    @property
    def changed(self) -> bool:
        return self.level is not self.previous


class StorageGuard:
    """Tracks free space on the download disk and answers the runner's questions."""

    def __init__(
        self,
        policy: Callable[[], StoragePolicy],
        folder: Callable[[], Path],
        *,
        free: Callable[[Path], int] | None = None,
        clock: Callable[[], float] = time.monotonic,
        interval: float = 1.0,
    ) -> None:
        self._policy = policy
        self._folder = folder
        self._free = free or (lambda path: disk_usage(path).free_bytes)
        self._clock = clock
        self._interval = interval
        self._level = StorageLevel.OK
        self._last = float("-inf")
        self._last_free: int | None = None

    @property
    def level(self) -> StorageLevel:
        return self._level

    def free_bytes(self) -> int | None:
        """Free space on the download disk now, or ``None`` if it cannot be read."""
        try:
            return int(self._free(self._folder()))
        except OSError:
            return None

    def low_storage(self) -> bool:
        """Whether downloads should keep little working data: asked for, or the disk is low."""
        return self._policy().low_storage_mode or self._level >= StorageLevel.LOW

    def reserved(self, active: Mapping[str, Mapping[str, Any] | None]) -> int:
        """What the running jobs still have to write, added up."""
        return sum(remaining_need(progress) for progress in active.values())

    def admit(self, need: int, active: Mapping[str, Mapping[str, Any] | None]) -> bool:
        """Whether a job needing about ``need`` more bytes may start."""
        free = self.free_bytes()
        if free is None:
            return True
        policy = self._policy()
        if self._level >= StorageLevel.PAUSE:
            return False
        floor = policy.pause_below or policy.stop_below or 0
        return free - self.reserved(active) - need >= floor

    def review(self, active: Mapping[str, Mapping[str, Any] | None]) -> GuardVerdict:
        """Look at free space (at most once per interval) and say what should happen."""
        now = self._clock()
        previous = self._level
        if now - self._last < self._interval:
            return GuardVerdict(previous, previous, self._last_free)
        self._last = now
        free = self.free_bytes()
        self._last_free = free
        policy = self._policy()
        if free is None or not policy.active:
            level = StorageLevel.OK
        else:
            level = policy.level_for(free, current=previous)
        self._level = level
        ids = tuple(sorted(active))
        return GuardVerdict(
            level=level,
            previous=previous,
            free_bytes=free,
            pause=ids if level is StorageLevel.PAUSE else (),
            stop=ids if level is StorageLevel.STOP else (),
            resume=previous >= StorageLevel.PAUSE and level < StorageLevel.PAUSE,
        )
