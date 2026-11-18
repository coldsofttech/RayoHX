"""``Queue``: the public face of the persistent download queue.

    rayo = Rayo()
    job = rayo.queue.add("https://example.com/master.m3u8", priority="high")
    rayo.queue.start()          # run jobs in this process
    rayo.queue.wait_idle()

Adding, listing, pausing and the other actions work whether or not a runner is active in this
process. When another process is the runner (for example ``rayohx queue run``), actions on its
running jobs are handed over through the database and carried out within a poll interval.
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import TYPE_CHECKING, Any

from rayohx.config import DownloadConfig, validate_url
from rayohx.errors import ConfigurationError
from rayohx.platform.errors import QueueError
from rayohx.platform.events import EventCategory
from rayohx.platform.jobs.model import (
    BulkResult,
    JobRecord,
    JobSpec,
    JobState,
    QueuePriority,
)
from rayohx.platform.jobs.names import safe_filename
from rayohx.platform.jobs.options import config_from_options, config_to_options
from rayohx.platform.jobs.retry import RetryPolicy
from rayohx.platform.queue.runner import CANCEL, PAUSE
from rayohx.redaction import redact_url
from rayohx.storage import FileLock

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

    from rayohx.platform.events import EventBus
    from rayohx.platform.persistence import SettingsStore
    from rayohx.platform.queue.repository import JobRepository
    from rayohx.platform.queue.runner import QueueRunner
    from rayohx.platform.secrets import SecretStore

JobList = list[JobRecord]
IdList = list[str]
DictList = list[dict[str, Any]]

MAX_ACTIVE_KEY = "queue.max_active"
_RANK_GAP = 1e-6


class Refused(Exception):
    """An action does not apply to a job; the message says why."""


def _ids(value: str | Iterable[str]) -> list[str]:
    return [value] if isinstance(value, str) else list(dict.fromkeys(value))


class Queue:
    """Add, order, control and inspect jobs."""

    def __init__(
        self,
        repository: JobRepository,
        runner: QueueRunner,
        bus: EventBus,
        secrets: SecretStore,
        settings: SettingsStore,
        *,
        download_dir: Path,
        runner_lock_path: Path | None = None,
    ) -> None:
        self._repo = repository
        self._runner = runner
        self._bus = bus
        self._secrets = secrets
        self._settings = settings
        self.download_dir = download_dir
        self._runner_lock_path = runner_lock_path
        saved = settings.get(MAX_ACTIVE_KEY)
        if isinstance(saved, int) and saved >= 1:
            runner.set_max_active(saved)

    # --- adding ----------------------------------------------------------------------------

    def add(
        self,
        url: str,
        *,
        config: DownloadConfig | None = None,
        options: Mapping[str, Any] | None = None,
        secrets: Mapping[str, Any] | None = None,
        priority: QueuePriority | str | int = QueuePriority.NORMAL,
        output_name: str | None = None,
        playlist_text: str | None = None,
        retry: RetryPolicy | None = None,
    ) -> JobRecord:
        """Queue one download.

        Give the settings as a ``DownloadConfig`` (``config``), or as stored ``options`` and
        ``secrets`` (as returned by ``config_to_options``). With neither, defaults are used. The
        settings are checked now, so a bad combination is refused here and not when the job runs.

        Raises:
            ConfigurationError: If the address, file name or settings are not valid.
        """
        address = validate_url(url)
        name = safe_filename(output_name) if output_name else None
        stored, hidden = self._split(config, options, secrets)
        if config is not None and config.output.path is not None:
            if name is not None:
                raise ConfigurationError("Give the file name once: output_name or output.path.")
            name = safe_filename(config.output.path.name)
            parent = config.output.path.parent
            if str(parent) not in {"", "."}:
                stored["output"] = {**stored.get("output", {}), "directory": str(parent)}
        config_from_options(stored, hidden, default_directory=self.download_dir)  # validate

        job_id = uuid.uuid4().hex[:12]
        ref = None
        if hidden:
            ref = f"job-{job_id}"
            self._secrets.put(ref, hidden)
        spec = JobSpec(
            url=address,
            options=stored,
            playlist_text=playlist_text,
            output_name=name,
            retry=retry or RetryPolicy(),
        )
        try:
            record = self._repo.insert(
                job_id=job_id,
                spec=spec,
                display_url=redact_url(address),
                priority=QueuePriority.parse(priority),
                rank=self._repo.next_rank(),
                secret_ref=ref,
            )
        except Exception:
            if ref:
                self._secrets.delete(ref)
            raise
        self._bus.emit(
            "queue.job_added",
            category=EventCategory.QUEUE,
            job_id=job_id,
            url=record.url,
            priority=record.priority.name.lower(),
        )
        self._runner.wake()
        return record

    def add_many(self, urls: Iterable[str], **kwargs: Any) -> JobList:
        """Queue several addresses with the same settings. Nothing is queued if one is invalid."""
        addresses = list(urls)
        for address in addresses:
            validate_url(address)
        return [self.add(address, **kwargs) for address in addresses]

    @staticmethod
    def _split(
        config: DownloadConfig | None,
        options: Mapping[str, Any] | None,
        secrets: Mapping[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if config is not None and options is not None:
            raise ConfigurationError("Give either config or options, not both.")
        if config is not None:
            stored, hidden = config_to_options(config)
            return stored, hidden
        return dict(options or {}), dict(secrets or {})

    # --- looking ---------------------------------------------------------------------------

    def get(self, job_id: str) -> JobRecord | None:
        record = self._repo.get(job_id)
        return None if record is None else self._live(record)

    def list(
        self,
        *,
        states: Iterable[JobState | str] | None = None,
        limit: int | None = None,
        newest_first: bool = False,
    ) -> JobList:
        """Jobs in the order they will run (or newest first)."""
        wanted = None if states is None else [JobState(s) for s in states]
        records = self._repo.select(states=wanted, limit=limit, queue_order=not newest_first)
        return [self._live(r) for r in records]

    def stats(self) -> dict[str, Any]:
        counts = self._repo.counts()
        return {
            "counts": counts,
            "total": sum(counts.values()),
            "active": len(self._runner.active_ids()),
            "max_active": self._runner.max_active,
            "runner": "this process"
            if self._runner.running
            else ("another process" if self._runner_elsewhere() else "none"),
        }

    def attempts(self, job_id: str) -> DictList:
        """The runs of a job, with how each one ended."""
        return self._repo.attempts(job_id)

    def _live(self, record: JobRecord) -> JobRecord:
        live = self._runner.progress(record.id)
        return dataclasses.replace(record, progress=live) if live else record

    # --- controlling -----------------------------------------------------------------------

    def pause(self, ids: str | Iterable[str]) -> BulkResult:
        """Stop jobs, keeping what they downloaded. A running job gives up its slot."""
        return self._bulk(ids, self._pause)

    def resume(self, ids: str | Iterable[str]) -> BulkResult:
        return self._bulk(ids, self._resume)

    def cancel(self, ids: str | Iterable[str]) -> BulkResult:
        return self._bulk(ids, self._cancel)

    def retry(self, ids: str | Iterable[str]) -> BulkResult:
        """Queue failed or cancelled jobs again, as if new (attempts start again from zero)."""
        return self._bulk(ids, self._retry)

    def remove(self, ids: str | Iterable[str]) -> BulkResult:
        """Forget jobs that are not running. Downloaded files are never deleted."""
        return self._bulk(ids, self._remove)

    def set_priority(
        self, ids: str | Iterable[str], priority: QueuePriority | str | int
    ) -> BulkResult:
        level = QueuePriority.parse(priority)
        return self._bulk(ids, lambda job: self._set_priority(job, level))

    def move_to_top(self, ids: str | Iterable[str]) -> BulkResult:
        """Put jobs first among the jobs of their priority, keeping their relative order."""
        selected = _ids(ids)
        result = BulkResult()
        floor = self._repo.rank_bounds()[0]
        for offset, job_id in enumerate(reversed(selected)):
            job = self._repo.get(job_id)
            if job is None:
                result.failed[job_id] = "No such job."
                continue
            self._repo.update(job_id, rank=floor - 1.0 - offset)
        for job_id in selected:
            if job_id not in result.failed:
                result.done.append(job_id)
        self._runner.wake()
        return result

    def move_to_bottom(self, ids: str | Iterable[str]) -> BulkResult:
        selected = _ids(ids)
        result = BulkResult()
        ceiling = self._repo.rank_bounds()[1]
        for offset, job_id in enumerate(selected, start=1):
            if self._repo.update(job_id, rank=ceiling + offset):
                result.done.append(job_id)
            else:
                result.failed[job_id] = "No such job."
        return result

    def move_before(self, job_id: str, target_id: str) -> JobRecord:
        """Put ``job_id`` just before ``target_id``. It takes the target's priority.

        Raises:
            QueueError: If either job does not exist.
        """
        job, target = self._repo.get(job_id), self._repo.get(target_id)
        if job is None or target is None:
            raise QueueError("No such job.")
        if job_id == target_id:
            return job
        for _ in range(2):
            target_rank = self._repo.rank_of(target_id)
            assert target_rank is not None  # noqa: S101
            below = self._repo.rank_below(int(target.priority), target_rank, exclude=job_id)
            low = target_rank - 2.0 if below is None else below
            new = (low + target_rank) / 2
            if target_rank - new > _RANK_GAP:
                self._repo.update(job_id, rank=new, priority=int(target.priority))
                break
            self._repo.renumber()  # ranks ran out of room between these two
        record = self._repo.get(job_id)
        assert record is not None  # noqa: S101
        return record

    @property
    def max_active(self) -> int:
        return self._runner.max_active

    @max_active.setter
    def max_active(self, value: int) -> None:
        if value < 1:
            raise ConfigurationError("max_active must be at least 1.")
        self._settings.set(MAX_ACTIVE_KEY, int(value))
        self._runner.set_max_active(value)

    # --- bulk plumbing and single-job actions ----------------------------------------------

    def _bulk(self, ids: str | Iterable[str], action: Any) -> BulkResult:
        result = BulkResult()
        for job_id in _ids(ids):
            job = self._repo.get(job_id)
            if job is None:
                result.failed[job_id] = "No such job."
                continue
            try:
                action(job)
            except Refused as why:
                result.failed[job_id] = str(why)
            else:
                result.done.append(job_id)
        self._runner.wake()
        return result

    def _runner_elsewhere(self) -> bool:
        """Whether another process is running the queue."""
        if self._runner.running or self._runner_lock_path is None:
            return False
        probe = FileLock(self._runner_lock_path)
        if probe.acquire():
            probe.release()
            return False
        return True

    def _stop_running(self, job: JobRecord, kind: str) -> None:
        """Pause or cancel a job that a runner is working on."""
        if self._runner.request(job.id, kind):
            return
        if self._runner_elsewhere():
            self._repo.update(job.id, control_request=kind)
            return
        # Nobody is running it: it was left behind by a crashed runner.
        target = JobState.PAUSED if kind == PAUSE else JobState.CANCELLED
        sources = [s for s in JobState if not s.is_terminal]
        if self._repo.transition(job.id, sources, target, control_request=None):
            self._emit_change(job, target)

    def _emit_change(self, job: JobRecord, new: JobState) -> None:
        self._bus.emit(
            "queue.job_state_changed",
            category=EventCategory.QUEUE,
            job_id=job.id,
            old=job.state.value,
            new=new.value,
        )
        if new.is_terminal:
            self._bus.emit(f"queue.job_{new.value}", category=EventCategory.QUEUE, job_id=job.id)

    def _settle(
        self, job: JobRecord, to: JobState, sources: Iterable[JobState], **fields: Any
    ) -> None:
        """Move a waiting job, or hand the job to whoever is running it if it just started."""
        if self._repo.transition(job.id, sources, to, **fields):
            self._emit_change(job, to)
            return
        latest = self._repo.get(job.id)
        if (
            latest is not None
            and latest.state.is_active
            and to in {JobState.PAUSED, JobState.CANCELLED}
        ):
            self._stop_running(latest, PAUSE if to is JobState.PAUSED else CANCEL)
            return
        state = latest.state.value if latest else "gone"
        raise Refused(f"The job is {state}.")

    def _pause(self, job: JobRecord) -> None:
        if job.state is JobState.PAUSED:
            return
        if job.state.is_terminal:
            raise Refused(f"The job is already {job.state.value}.")
        if job.state.is_active:
            self._stop_running(job, PAUSE)
        else:
            self._settle(job, JobState.PAUSED, [JobState.QUEUED])

    def _resume(self, job: JobRecord) -> None:
        if job.state is not JobState.PAUSED:
            if job.state is JobState.QUEUED:
                return
            raise Refused(f"Only a paused job can be resumed; this one is {job.state.value}.")
        self._settle(job, JobState.QUEUED, [JobState.PAUSED], not_before=None)

    def _cancel(self, job: JobRecord) -> None:
        if job.state.is_terminal:
            raise Refused(f"The job is already {job.state.value}.")
        if job.state.is_active:
            self._stop_running(job, CANCEL)
        else:
            self._settle(
                job,
                JobState.CANCELLED,
                [JobState.QUEUED, JobState.PAUSED],
                finished_at=self._repo.now(),
            )

    def _retry(self, job: JobRecord) -> None:
        if job.state not in {JobState.FAILED, JobState.CANCELLED}:
            raise Refused(
                f"Only a failed or cancelled job can be retried; this one is {job.state.value}."
            )
        self._settle(
            job,
            JobState.QUEUED,
            [JobState.FAILED, JobState.CANCELLED],
            attempts=0,
            error_code=None,
            error_message=None,
            not_before=None,
            finished_at=None,
            recovered=False,
        )

    def _remove(self, job: JobRecord) -> None:
        if job.state.is_active:
            raise Refused("Cancel the job before removing it.")
        ref = self._repo.secret_ref(job.id)
        if not self._repo.delete(job.id):
            raise Refused("The job is already gone.")
        if ref:
            self._secrets.delete(ref)
        self._bus.emit("queue.job_removed", category=EventCategory.QUEUE, job_id=job.id)

    def _set_priority(self, job: JobRecord, level: QueuePriority) -> None:
        if job.state.is_terminal:
            raise Refused(f"The job is already {job.state.value}.")
        self._repo.update(job.id, priority=int(level))
        self._bus.emit(
            "queue.job_priority_changed",
            category=EventCategory.QUEUE,
            job_id=job.id,
            priority=level.name.lower(),
        )

    # --- credentials -----------------------------------------------------------------------

    def provide_credentials(self, job_id: str, secrets: Mapping[str, Any]) -> JobRecord:
        """Supply the secrets of a job that lost them (after a restart without a keyring)."""
        job = self._repo.get(job_id)
        if job is None:
            raise QueueError("No such job.")
        ref = self._repo.secret_ref(job_id) or f"job-{job_id}"
        self._secrets.put(ref, dict(secrets))
        self._repo.update(job_id, secret_ref=ref, needs_credentials=False)
        self._runner.wake()
        latest = self._repo.get(job_id)
        assert latest is not None  # noqa: S101
        return latest

    # --- export and import -----------------------------------------------------------------

    def export(self, ids: str | Iterable[str] | None = None) -> DictList:
        """The jobs as plain data, without secrets, to save or move to another queue."""
        jobs = (
            self._repo.select()
            if ids is None
            else [j for i in _ids(ids) if (j := self._repo.get(i)) is not None]
        )
        return [
            {
                "url": j.spec.url,
                "options": dict(j.spec.options),
                "playlist_text": j.spec.playlist_text,
                "output_name": j.spec.output_name,
                "priority": j.priority.name.lower(),
                "retry": j.spec.retry.to_dict(),
            }
            for j in jobs
        ]

    def import_jobs(self, items: Iterable[Mapping[str, Any]]) -> JobList:
        """Queue jobs from ``export``. Everything is checked first; nothing is queued on error."""
        prepared = []
        for item in items:
            prepared.append(
                {
                    "url": item["url"],
                    "options": item.get("options") or {},
                    "playlist_text": item.get("playlist_text"),
                    "output_name": item.get("output_name"),
                    "priority": item.get("priority", "normal"),
                    "retry": RetryPolicy.from_dict(item.get("retry") or {}),
                }
            )
        for item in prepared:
            validate_url(item["url"])
            config_from_options(item["options"], {}, default_directory=self.download_dir)
        return [
            self.add(
                p["url"],
                options=p["options"],
                playlist_text=p["playlist_text"],
                output_name=p["output_name"],
                priority=p["priority"],
                retry=p["retry"],
            )
            for p in prepared
        ]

    # --- running ---------------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._runner.running

    def start(self) -> IdList:
        """Run jobs in this process. Returns the ids of interrupted jobs that were requeued.

        Raises:
            RunnerLockedError: If another process is already running the queue.
        """
        return self._runner.start()

    def stop(self, timeout: float = 30.0) -> None:
        self._runner.stop(timeout)

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Wait until no job is running or waiting to run."""
        return self._runner.wait_idle(timeout)
