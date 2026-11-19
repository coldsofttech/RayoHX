"""Finding what can be cleaned up, and cleaning it safely.

Nothing here can touch a finished download. The only things ever removed are:

* working folders (resume state and half-downloaded data) that no running download holds, that
  belong to no job that could still resume, and that are older than a limit;
* diagnostic reports older than a limit;
* optionally, records of finished jobs and old log entries (never their files).

``plan`` only looks. ``apply`` re-checks each item at the moment it acts, so a folder a download
has just picked up is left alone.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rayohx.platform.jobs.model import ACTIVE_STATES, JobState
from rayohx.storage import find_workspaces, folder_size, is_workspace_in_use, last_used

if TYPE_CHECKING:
    from collections.abc import Callable

    from rayohx.platform.events import EventStore
    from rayohx.platform.queue.repository import JobRepository

DAY = 86400.0
#: States of a job that could still use its working folder to resume.
_RESUMABLE = frozenset({JobState.QUEUED, JobState.PAUSED, *ACTIVE_STATES})


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkspaceReport:
    """One working folder: whose it is, how big, and whether it is safe to remove."""

    path: Path
    size_bytes: int
    age_days: float
    in_use: bool
    job_id: str | None = None
    job_state: str | None = None
    #: Whether removing it loses nothing a job could still use.
    safe_to_remove: bool = True
    reason: str = ""

    @property
    def name(self) -> str:
        return self.path.name

    def to_dict(self, *, full_path: bool = False) -> dict[str, Any]:
        return {
            "name": self.name,
            **({"path": str(self.path)} if full_path else {}),
            "size_bytes": self.size_bytes,
            "age_days": round(self.age_days, 2),
            "in_use": self.in_use,
            "job_id": self.job_id,
            "job_state": self.job_state,
            "safe_to_remove": self.safe_to_remove,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class CleanupItem:
    """One thing the plan would remove."""

    kind: str  # "workspace", "report", "job_record" or "event_log"
    name: str
    size_bytes: int
    age_days: float
    reason: str
    path: Path | None = None
    ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "size_bytes": self.size_bytes,
            "age_days": round(self.age_days, 2),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class CleanupPlan:
    items: tuple[CleanupItem, ...] = ()
    #: Things that were looked at and deliberately kept, with the reason.
    kept: tuple[str, ...] = ()

    @property
    def total_bytes(self) -> int:
        return sum(i.size_bytes for i in self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [i.to_dict() for i in self.items],
            "total_bytes": self.total_bytes,
            "kept": list(self.kept),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class CleanupResult:
    plan: CleanupPlan
    dry_run: bool
    removed: tuple[CleanupItem, ...] = ()
    skipped: tuple[str, ...] = ()

    @property
    def freed_bytes(self) -> int:
        return sum(i.size_bytes for i in self.removed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "planned": [i.to_dict() for i in self.plan.items],
            "removed": [i.to_dict() for i in self.removed],
            "freed_bytes": self.freed_bytes,
            "skipped": list(self.skipped),
            "kept": list(self.plan.kept),
        }


def looks_like_workspace(path: Path) -> bool:
    """Whether a folder has the shape of an engine working folder (and is not a link)."""
    if path.is_symlink() or not path.is_dir():
        return False
    return path.name.startswith(".rayohx-") or (path / "state.json").is_file()


class Cleaner:
    """Inspects working folders and removes the abandoned ones."""

    def __init__(
        self,
        repository: JobRepository,
        events: EventStore,
        *,
        download_dir: Callable[[], Path],
        reports: Callable[[], list[tuple[int, Path, float]]],
        forget_report: Callable[[int], None],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._jobs = repository
        self._events = events
        self._download_dir = download_dir
        self._reports = reports
        self._forget_report = forget_report
        self._clock = clock

    # --- looking ---------------------------------------------------------------------------

    def folders(self) -> list[Path]:
        """Every working folder we know of: the ones in the download folder and the registered."""
        found = dict.fromkeys(find_workspaces(self._download_dir()))
        for text in self._jobs.workspace_owners():
            path = Path(text)
            if looks_like_workspace(path):
                found.setdefault(path, None)
        return sorted(found)

    def workspaces(self) -> list[WorkspaceReport]:
        owners = self._jobs.workspace_owners()
        now = self._clock()
        reports = []
        for path in self.folders():
            try:
                size, used = folder_size(path), is_workspace_in_use(path)
                age = max(0.0, (now - last_used(path)) / DAY)
            except OSError:
                continue
            owner = owners.get(str(path))
            job = self._jobs.get(owner) if owner else None
            state = job.state if job else None
            safe, reason = self._judge(used, owner, state)
            reports.append(
                WorkspaceReport(
                    path=path,
                    size_bytes=size,
                    age_days=age,
                    in_use=used,
                    job_id=owner if job else None,
                    job_state=state.value if state else None,
                    safe_to_remove=safe,
                    reason=reason,
                )
            )
        return reports

    @staticmethod
    def _judge(in_use: bool, owner: str | None, state: JobState | None) -> tuple[bool, str]:
        if in_use:
            return False, "a download is using it right now"
        if state in _RESUMABLE:
            return False, f"its job is {state.value}; removing it would restart that download"
        if state in {JobState.FAILED, JobState.CANCELLED}:
            return True, f"its job {state.value}; only a retry would use it"
        if state is JobState.COMPLETED:
            return True, "its job finished; this is left over"
        if owner:
            return True, "its job was removed"
        return True, "no job in the queue owns it (an interrupted command-line download?)"

    # --- planning and doing ----------------------------------------------------------------

    def plan(
        self,
        *,
        older_than_days: float = 7,
        report_days: float | None = 30,
        job_days: float | None = None,
        event_days: float | None = None,
    ) -> CleanupPlan:
        items: list[CleanupItem] = []
        kept: list[str] = []
        for w in self.workspaces():
            if not w.safe_to_remove:
                kept.append(f"{w.name}: {w.reason}")
            elif w.age_days < older_than_days:
                kept.append(f"{w.name}: used {w.age_days:.1f} days ago, newer than the limit")
            else:
                items.append(
                    CleanupItem(
                        kind="workspace", name=w.name, size_bytes=w.size_bytes,
                        age_days=w.age_days, reason=w.reason, path=w.path,
                    )
                )  # fmt: skip
        now = self._clock()
        if report_days is not None:
            for report_id, path, created in self._reports():
                age = (now - created) / DAY
                if age >= report_days:
                    size = path.stat().st_size if path.is_file() else 0
                    items.append(
                        CleanupItem(
                            kind="report", name=path.name, size_bytes=size, age_days=age,
                            reason="an old diagnostic report", path=path, ref=str(report_id),
                        )
                    )  # fmt: skip
        if job_days is not None:
            for job in self._jobs.select(
                states=[JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED]
            ):
                age = (now - (job.finished_at or job.updated_at)) / DAY
                if age >= job_days:
                    items.append(
                        CleanupItem(
                            kind="job_record", name=job.id, size_bytes=0, age_days=age,
                            reason=f"the record of a {job.state.value} job (its file is kept)",
                            ref=job.id,
                        )
                    )  # fmt: skip
        if event_days is not None:
            items.append(
                CleanupItem(
                    kind="event_log", name="events", size_bytes=0, age_days=event_days,
                    reason=f"log entries older than {event_days:g} days", ref=str(event_days),
                )
            )  # fmt: skip
        return CleanupPlan(items=tuple(items), kept=tuple(kept))

    def apply(self, plan: CleanupPlan, *, dry_run: bool = True) -> CleanupResult:
        """Carry out ``plan``. By default nothing is removed: it only reports what would be."""
        if dry_run:
            return CleanupResult(plan=plan, dry_run=True)
        removed: list[CleanupItem] = []
        skipped: list[str] = []
        for item in plan.items:
            try:
                if self._remove(item):
                    removed.append(item)
                else:
                    skipped.append(f"{item.name}: no longer safe to remove")
            except OSError as exc:
                skipped.append(f"{item.name}: {exc.strerror or exc}")
        return CleanupResult(
            plan=plan, dry_run=False, removed=tuple(removed), skipped=tuple(skipped)
        )

    def _remove(self, item: CleanupItem) -> bool:
        if item.kind == "workspace" and item.path is not None:
            # Look again: a download may have picked the folder up since the plan was made.
            if not looks_like_workspace(item.path) or is_workspace_in_use(item.path):
                return False
            owner = self._jobs.workspace_owners().get(str(item.path))
            job = self._jobs.get(owner) if owner else None
            if job is not None and job.state in _RESUMABLE:
                return False
            shutil.rmtree(item.path, ignore_errors=True)
            self._jobs.forget_workspace(str(item.path))
            return True
        if item.kind == "report" and item.path is not None and item.ref is not None:
            item.path.unlink(missing_ok=True)
            self._forget_report(int(item.ref))
            return True
        if item.kind == "job_record" and item.ref is not None:
            job = self._jobs.get(item.ref)
            if job is None or job.state.is_terminal is False:
                return False
            return self._jobs.delete(item.ref)
        if item.kind == "event_log" and item.ref is not None:
            self._events.prune(older_than=self._clock() - float(item.ref) * DAY)
            return True
        return False
