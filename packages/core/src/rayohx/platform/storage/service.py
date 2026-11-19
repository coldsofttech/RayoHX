"""``rayo.storage``: how much room there is, who uses it, and what can be cleaned up."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rayohx.platform.jobs.model import JobState
from rayohx.platform.storage.cleanup import Cleaner, CleanupPlan, CleanupResult, WorkspaceReport
from rayohx.platform.storage.guard import StorageGuard, remaining_need
from rayohx.platform.storage.policy import (
    StorageLevel,
    StoragePolicy,
    load_policy,
    save_policy,
)
from rayohx.storage import DiskUsage, disk_usage

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from rayohx.platform.diagnostics.registry import ReportRegistry
    from rayohx.platform.events import EventStore
    from rayohx.platform.paths import PlatformPaths
    from rayohx.platform.persistence import SettingsStore
    from rayohx.platform.queue.repository import JobRepository


@dataclass(frozen=True, slots=True, kw_only=True)
class VolumeUsage:
    """A disk that matters to the queue."""

    role: str  # "downloads" or "data"
    usage: DiskUsage
    level: StorageLevel

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            **self.usage.to_dict(),
            "level": self.level.name.lower(),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class StorageSnapshot:
    """Everything about disk use at one moment."""

    taken_at: float
    policy: StoragePolicy
    level: StorageLevel
    volumes: tuple[VolumeUsage, ...]
    #: Size of the finished downloads the queue made.
    output_bytes: int
    #: Working folders of all kinds, and how many.
    workspace_bytes: int
    workspace_count: int
    #: The part of that no finished download needs: interrupted and abandoned work.
    incomplete_bytes: int
    #: Working data held by downloads running now.
    active_bytes: int
    #: What running downloads still have to write.
    reserved_bytes: int
    #: The most working space any download has used at one time.
    peak_temporary_bytes: int
    #: The queue's own files: the database and saved reports.
    data_bytes: int
    free_after_reservations: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "taken_at": self.taken_at,
            "level": self.level.name.lower(),
            "policy": self.policy.to_dict(),
            "volumes": [v.to_dict() for v in self.volumes],
            "output_bytes": self.output_bytes,
            "workspace_bytes": self.workspace_bytes,
            "workspace_count": self.workspace_count,
            "incomplete_bytes": self.incomplete_bytes,
            "active_bytes": self.active_bytes,
            "reserved_bytes": self.reserved_bytes,
            "peak_temporary_bytes": self.peak_temporary_bytes,
            "data_bytes": self.data_bytes,
            "free_after_reservations": self.free_after_reservations,
        }


class StorageService:
    """Disk accounting, the low-space policy and cleanup."""

    def __init__(
        self,
        repository: JobRepository,
        settings: SettingsStore,
        events: EventStore,
        reports: ReportRegistry,
        paths: PlatformPaths,
        *,
        download_dir: Path,
        guard: StorageGuard,
        live_progress: Callable[[], Mapping[str, Mapping[str, Any] | None]] = dict,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._jobs = repository
        self._settings = settings
        self._paths = paths
        self.download_dir = download_dir
        self._live = live_progress
        self._clock = clock
        self._policy_cache: StoragePolicy | None = None
        self.guard = guard
        self.cleaner = Cleaner(
            repository,
            events,
            download_dir=lambda: self.download_dir,
            reports=reports.entries,
            forget_report=reports.forget,
            clock=clock,
        )

    # --- policy ----------------------------------------------------------------------------

    def policy(self) -> StoragePolicy:
        """The thresholds in force. Read each time, so another process's change is seen."""
        return load_policy(self._settings)

    def set_policy(self, policy: StoragePolicy) -> StoragePolicy:
        save_policy(self._settings, policy)
        return policy

    # --- looking ---------------------------------------------------------------------------

    def snapshot(self) -> StorageSnapshot:
        policy = self.policy()
        live = self._live()
        reserved = self.guard.reserved(live)
        volumes = []
        free_after: int | None = None
        for role, path in (("downloads", self.download_dir), ("data", self._paths.data_dir)):
            try:
                usage = disk_usage(path)
            except OSError:
                continue
            level = policy.level_for(usage.free_bytes) if role == "downloads" else StorageLevel.OK
            volumes.append(VolumeUsage(role=role, usage=usage, level=level))
            if role == "downloads":
                free_after = max(0, usage.free_bytes - reserved)
        workspaces = self.workspaces()
        incomplete = sum(
            w.size_bytes for w in workspaces if w.job_state != JobState.COMPLETED.value
        )
        peak = max(
            self._jobs.peak_temporary_bytes(),
            *(int((p or {}).get("peak_temporary_bytes") or 0) for p in live.values()),
            0,
        )
        active = sum(int((p or {}).get("working_bytes") or 0) for p in live.values())
        return StorageSnapshot(
            taken_at=self._clock(),
            policy=policy,
            level=self.guard.level,
            volumes=tuple(volumes),
            output_bytes=self._jobs.finished_output_bytes(),
            workspace_bytes=sum(w.size_bytes for w in workspaces),
            workspace_count=len(workspaces),
            incomplete_bytes=incomplete,
            active_bytes=active,
            reserved_bytes=reserved,
            peak_temporary_bytes=peak,
            data_bytes=self._data_bytes(),
            free_after_reservations=free_after,
        )

    def _data_bytes(self) -> int:
        total = 0
        for folder in (self._paths.data_dir,):
            try:
                for item in folder.rglob("*"):
                    if item.is_file() and not item.is_symlink():
                        total += item.stat().st_size
            except OSError:
                continue
        return total

    def workspaces(self) -> list[WorkspaceReport]:
        """Every working folder, whose it is, and whether it is safe to remove."""
        return self.cleaner.workspaces()

    def job_usage(self, job_id: str) -> dict[str, Any] | None:
        """What one job holds on disk: its output, working folders and live working data."""
        job = self._jobs.get(job_id)
        if job is None:
            return None
        owned = set(self._jobs.workspaces_of(job_id))
        folders = [w for w in self.workspaces() if str(w.path) in owned]
        live = self._live().get(job_id) or job.progress or {}
        return {
            "job_id": job_id,
            "output_bytes": job.output_size or 0,
            "workspace_bytes": sum(w.size_bytes for w in folders),
            "workspaces": [w.to_dict() for w in folders],
            "working_bytes": int(live.get("working_bytes") or 0),
            "peak_temporary_bytes": int(
                live.get("peak_temporary_bytes")
                or ((job.result or {}).get("storage") or {}).get("peak_temporary_bytes")
                or 0
            ),
            "still_to_write": remaining_need(live),
        }

    # --- cleaning --------------------------------------------------------------------------

    def plan_cleanup(self, **limits: Any) -> CleanupPlan:
        """What cleaning up would remove, with the reason for each and what is kept."""
        return self.cleaner.plan(**limits)

    def cleanup(self, *, dry_run: bool = True, **limits: Any) -> CleanupResult:
        """Remove abandoned working folders and old reports. Looks only, unless told not to."""
        return self.cleaner.apply(self.cleaner.plan(**limits), dry_run=dry_run)
