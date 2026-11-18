"""Running queued jobs: the scheduler loop and one worker thread per active job.

Exactly one runner works on a data folder at a time (it holds ``runner.lock``). Other processes,
such as the command line, change jobs in the database; the runner notices within one poll interval.

How a job ends depends on *why* its run stopped:

=============  ===========================================================================
completed      the job is ``COMPLETED``.
failed         retried after a delay if the policy allows it, else ``FAILED``.
pause          ``PAUSED``. The run is cancelled but its resume state is kept, so the job
               gives up its slot and its lock, and continues where it stopped.
cancel         ``CANCELLED``.
shutdown       back to ``QUEUED``, so it starts again with the next runner.
=============  ===========================================================================

A crash is handled at the next start: jobs left in an active state go back to ``QUEUED`` marked
``recovered``, and the engine resumes them from its own state file.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rayohx.cancellation import CancellationToken
from rayohx.downloader import Downloader
from rayohx.enums import DownloadState, VerificationStatus
from rayohx.errors import ConfigurationError, RayoHXError
from rayohx.platform.errors import QueueError, RunnerLockedError
from rayohx.platform.events import EventCategory, Severity
from rayohx.platform.jobs.model import ACTIVE_STATES, ENGINE_STATE_TO_JOB, JobRecord, JobState
from rayohx.platform.jobs.options import config_from_options
from rayohx.platform.queue.scheduler import Candidate, pick_next
from rayohx.serialization import progress_to_dict
from rayohx.storage import FileLock

if TYPE_CHECKING:
    from collections.abc import Callable

    from rayohx.config import DownloadConfig
    from rayohx.events import DownloadEvent
    from rayohx.models import DownloadResult
    from rayohx.platform.events import EventBus
    from rayohx.platform.queue.repository import JobRepository
    from rayohx.platform.secrets import SecretStore

logger = logging.getLogger(__name__)

PAUSE = "pause"
CANCEL = "cancel"
SHUTDOWN = "shutdown"


@dataclass(slots=True)
class _Active:
    token: CancellationToken = field(default_factory=CancellationToken)
    thread: threading.Thread | None = None
    #: Why the run was stopped, if it was: ``pause``, ``cancel`` or ``shutdown``.
    intent: str | None = None
    state: JobState = JobState.PREPARING
    progress: dict[str, Any] | None = None


class QueueRunner:
    """Starts queued jobs as slots free up and records how each one ends."""

    def __init__(
        self,
        repository: JobRepository,
        bus: EventBus,
        secrets: SecretStore,
        *,
        download_dir: Path,
        lock_path: Path | None = None,
        max_active: int = 2,
        poll_interval: float = 0.5,
        clock: Callable[[], float] = time.time,
        downloader_factory: Callable[..., Downloader] = Downloader,
        admit: Callable[[Candidate], bool] | None = None,
    ) -> None:
        self._repo = repository
        self._bus = bus
        self._secrets = secrets
        self._download_dir = download_dir
        self._lock = FileLock(lock_path) if lock_path is not None else None
        self._max_active = max(1, max_active)
        self._poll = poll_interval
        self._clock = clock
        self._factory = downloader_factory
        self._admit = admit
        self._cond = threading.Condition(threading.RLock())
        self._active: dict[str, _Active] = {}
        #: Every worker thread until it has fully finished, including its last bookkeeping.
        self._workers: set[threading.Thread] = set()
        self._thread: threading.Thread | None = None
        self._stopping = False
        self._busy = False

    # --- controlling the runner ------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def max_active(self) -> int:
        return self._max_active

    def set_max_active(self, value: int) -> None:
        """Change how many jobs run at once. Takes effect for the next job to start."""
        with self._cond:
            self._max_active = max(1, int(value))
            self._cond.notify_all()

    def start(self) -> list[str]:
        """Take the runner lock, recover interrupted jobs and start scheduling.

        Returns the ids of the jobs that were found half way and put back in the queue.

        Raises:
            RunnerLockedError: If another process is already running the queue.
        """
        if self.running:
            return []
        if self._lock is not None and not self._lock.acquire():
            raise RunnerLockedError
        self._stopping = False
        recovered = self._repo.recover_active()
        for job_id in recovered:
            self._bus.emit(
                "queue.job_recovered",
                category=EventCategory.QUEUE,
                severity=Severity.WARNING,
                job_id=job_id,
            )
        self._thread = threading.Thread(target=self._loop, name="rayohx-queue", daemon=True)
        self._thread.start()
        return recovered

    def stop(self, timeout: float = 30.0) -> None:
        """Stop starting jobs, put running ones back in the queue and release the lock.

        A running job is cancelled with its resume state kept. If one does not stop within
        ``timeout`` seconds the next runner recovers it.
        """
        with self._cond:
            self._stopping = True
            for active in self._active.values():
                active.intent = SHUTDOWN
                active.token.cancel()
            self._cond.notify_all()
        deadline = time.monotonic() + timeout
        thread = self._thread
        if thread is not None:
            thread.join(max(0.0, deadline - time.monotonic()))
        with self._cond:
            workers = list(self._workers)
        for worker in workers:
            worker.join(max(0.0, deadline - time.monotonic()))
        self._thread = None
        if self._lock is not None:
            self._lock.release()

    def wake(self) -> None:
        """Look at the queue now instead of at the next poll."""
        with self._cond:
            self._cond.notify_all()

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Wait until nothing is running or waiting to run. False if ``timeout`` ran out."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            if not self._active and not self._busy and self._repo.waiting_count() == 0:
                return True
            if deadline is not None and time.monotonic() >= deadline:
                return False
            with self._cond:
                self._cond.wait(0.05)

    # --- what the queue front end asks of a running job ------------------------------------

    def owns(self, job_id: str) -> bool:
        """Whether this runner is working on ``job_id`` right now."""
        with self._cond:
            return job_id in self._active

    def active_ids(self) -> list[str]:
        with self._cond:
            return sorted(self._active)

    def progress(self, job_id: str) -> dict[str, Any] | None:
        with self._cond:
            active = self._active.get(job_id)
            return dict(active.progress) if active and active.progress else None

    def request(self, job_id: str, kind: str) -> bool:
        """Stop a running job for ``kind`` (``pause`` or ``cancel``). False if it is not running."""
        if kind not in {PAUSE, CANCEL}:
            raise QueueError(f"Unknown request {kind!r}.")
        with self._cond:
            active = self._active.get(job_id)
            if active is None:
                return False
            if active.intent != CANCEL:  # cancelling wins over pausing
                active.intent = kind
            active.token.cancel()
            self._cond.notify_all()
            return True

    # --- the scheduler loop ----------------------------------------------------------------

    def _loop(self) -> None:
        while True:
            with self._cond:
                if self._stopping:
                    return
            try:
                self._tick()
            except Exception:
                logger.exception("The queue loop hit an error and will go on.")
            with self._cond:
                if self._stopping:
                    return
                self._cond.wait(self._wait_time())

    def _wait_time(self) -> float:
        delay = self._repo.next_delay(self._clock())
        return self._poll if delay is None else max(0.01, min(self._poll, delay))

    def _tick(self) -> None:
        self._apply_controls()
        self._dispatch()
        self._check_idle()

    def _apply_controls(self) -> None:
        """Carry out pause and cancel requests that other processes wrote to the database."""
        for job_id, kind in self._repo.control_requests():
            if self.request(job_id, kind):
                self._repo.update(job_id, control_request=None)
                continue
            job = self._repo.get(job_id)
            if job is None:
                continue
            # Not running here: it is waiting, or an earlier runner died with it.
            target = JobState.PAUSED if kind == PAUSE else JobState.CANCELLED
            sources = [JobState.QUEUED, JobState.PAUSED, *ACTIVE_STATES]
            done = {"finished_at": self._clock()} if target is JobState.CANCELLED else {}
            self._repo.transition(job_id, sources, target, control_request=None, **done)
            self._changed(job, target)

    def _dispatch(self) -> None:
        with self._cond:
            if self._stopping:
                return
            free = self._max_active - len(self._active)
        if free <= 0:
            return
        now = self._clock()
        for job_id in pick_next(self._repo.ready(now), free_slots=free, now=now, admit=self._admit):
            self._claim(job_id)

    def _claim(self, job_id: str) -> None:
        job = self._repo.get(job_id)
        if job is None:
            return
        claimed = self._repo.transition(
            job_id,
            [JobState.QUEUED],
            JobState.PREPARING,
            attempts=job.attempts + 1,
            started_at=self._clock(),
            finished_at=None,
            error_code=None,
            error_message=None,
            not_before=None,
            control_request=None,
        )
        if not claimed:
            return
        active = _Active()
        worker = threading.Thread(
            target=self._work, args=(job_id, active), name=f"rayohx-job-{job_id}", daemon=True
        )
        active.thread = worker
        with self._cond:
            self._active[job_id] = active
            self._workers.add(worker)
            self._busy = True
        self._changed(job, JobState.PREPARING)
        active.thread.start()

    def _check_idle(self) -> None:
        """Announce, once, that the queue has run dry after doing some work."""
        with self._cond:
            if not self._busy or self._active:
                return
        if self._repo.waiting_count() != 0:
            return
        with self._cond:
            if not self._busy or self._active:
                return
            self._busy = False
        self._bus.emit("queue.completed", category=EventCategory.QUEUE, counts=self._repo.counts())

    # --- one job ---------------------------------------------------------------------------

    def _work(self, job_id: str, active: _Active) -> None:
        attempt_id: int | None = None
        result: DownloadResult | None = None
        error: BaseException | None = None
        try:
            job = self._repo.get(job_id)
            if job is None:
                return
            config = self._load_config(job)
            if config is None:
                return  # waiting for credentials; already put back in the queue
            output = self._output_path(job, config)
            attempt_id = self._repo.begin_attempt(job_id, job.attempts)
            downloader = self._factory(
                job.spec.url,
                output=output,
                config=config,
                cancel=active.token,
                download_id=job_id,
                playlist_text=job.spec.playlist_text,
            )
            downloader.events.subscribe(partial(self._on_event, job_id, active))
            result = downloader.run()
            error = downloader.exception
        except BaseException as exc:
            error = exc
            if not isinstance(exc, RayoHXError):
                logger.exception("Job %s failed unexpectedly.", job_id)
        finally:
            try:
                self._finish(job_id, active, attempt_id, result, error)
            except Exception:
                logger.exception("Could not record how job %s ended.", job_id)
            with self._cond:
                self._active.pop(job_id, None)
            try:
                self._check_idle()  # announce "queue completed" before anyone sees it idle
            except Exception:
                logger.exception("Could not check whether the queue is idle.")
            with self._cond:
                self._workers.discard(threading.current_thread())
                self._cond.notify_all()

    def _load_config(self, job: JobRecord) -> DownloadConfig | None:
        ref = self._repo.secret_ref(job.id)
        secrets: dict[str, Any] = {}
        if ref is not None:
            found = self._secrets.get(ref)
            if found is None:
                self._repo.transition(
                    job.id,
                    ACTIVE_STATES,
                    JobState.QUEUED,
                    needs_credentials=True,
                    attempts=max(0, job.attempts - 1),
                )
                self._bus.emit(
                    "queue.job_needs_credentials",
                    category=EventCategory.QUEUE,
                    severity=Severity.WARNING,
                    job_id=job.id,
                )
                return None
            secrets = found
        config = config_from_options(
            job.spec.options, secrets, default_directory=self._download_dir
        )
        # A run that is paused, cancelled or interrupted must keep what it has downloaded.
        return dataclasses.replace(
            config, storage=dataclasses.replace(config.storage, keep_state_on_failure=True)
        )

    def _output_path(self, job: JobRecord, config: DownloadConfig) -> Path | None:
        if not job.spec.output_name:
            return None
        return (config.output.directory or self._download_dir) / job.spec.output_name

    def _on_event(self, job_id: str, active: _Active, event: DownloadEvent) -> None:
        if event.progress is not None:
            active.progress = progress_to_dict(event.progress)
        mapped = ENGINE_STATE_TO_JOB.get(event.state)
        if mapped is not None and mapped is not active.state:
            old, active.state = active.state, mapped
            if self._repo.transition(
                job_id, ACTIVE_STATES, mapped, progress_json=self._progress_json(active)
            ):
                self._bus.emit(
                    "queue.job_state_changed",
                    category=EventCategory.QUEUE,
                    job_id=job_id,
                    old=old.value,
                    new=mapped.value,
                )
        self._bus.forward(event, job_id=job_id)

    @staticmethod
    def _progress_json(active: _Active) -> str | None:
        return json.dumps(active.progress) if active.progress else None

    def _finish(
        self,
        job_id: str,
        active: _Active,
        attempt_id: int | None,
        result: DownloadResult | None,
        error: BaseException | None,
    ) -> None:
        now = self._clock()
        job = self._repo.get(job_id)
        if job is None:  # removed while it ran
            return
        progress = self._progress_json(active)
        if result is not None:
            progress = json.dumps(progress_to_dict(result.progress))
        code = error.code if isinstance(error, RayoHXError) else ("INTERNAL" if error else None)
        message = (
            result.error if result is not None and result.error else (str(error) if error else None)
        )

        if result is not None and result.state is DownloadState.COMPLETED:
            out = result.output
            self._repo.transition(
                job_id,
                ACTIVE_STATES,
                JobState.COMPLETED,
                finished_at=now,
                output_path=str(out.path) if out else None,
                output_size=out.size_bytes if out else None,
                progress_json=progress,
                control_request=None,
                **self._outcome(result),
            )
            self._end_attempt(attempt_id, "completed", None, None)
            self._changed(job, JobState.COMPLETED, severity=Severity.INFO)
            return

        cancelled = (result is not None and result.state is DownloadState.CANCELLED) or (
            active.token.is_cancelled and result is None
        )
        if cancelled:
            self._end_attempt(attempt_id, active.intent or "cancel", None, None)
            if active.intent == PAUSE:
                self._repo.transition(
                    job_id,
                    ACTIVE_STATES,
                    JobState.PAUSED,
                    progress_json=progress,
                    control_request=None,
                )
                self._changed(job, JobState.PAUSED)
            elif active.intent == SHUTDOWN:
                self._repo.transition(
                    job_id,
                    ACTIVE_STATES,
                    JobState.QUEUED,
                    progress_json=progress,
                    attempts=max(0, job.attempts - 1),
                    control_request=None,
                )
                self._changed(job, JobState.QUEUED)
            else:
                self._repo.transition(
                    job_id,
                    ACTIVE_STATES,
                    JobState.CANCELLED,
                    finished_at=now,
                    progress_json=progress,
                    control_request=None,
                )
                self._changed(job, JobState.CANCELLED)
            return

        # A failure.
        self._end_attempt(attempt_id, "failed", code, message)
        permanent = isinstance(error, ConfigurationError)
        if not permanent and job.spec.retry.should_retry(error, job.attempts):
            delay = job.spec.retry.delay_for(job.attempts)
            self._repo.transition(
                job_id,
                ACTIVE_STATES,
                JobState.QUEUED,
                error_code=code,
                error_message=message,
                not_before=now + delay,
                progress_json=progress,
                control_request=None,
            )
            self._bus.emit(
                "queue.job_retry_scheduled",
                category=EventCategory.QUEUE,
                severity=Severity.WARNING,
                job_id=job_id,
                attempt=job.attempts,
                max_attempts=job.spec.retry.max_attempts,
                delay_seconds=delay,
                code=code,
                error=message,
            )
            return
        self._repo.transition(
            job_id,
            ACTIVE_STATES,
            JobState.FAILED,
            finished_at=now,
            error_code=code,
            error_message=message,
            progress_json=progress,
            control_request=None,
            **self._outcome(result),
        )
        self._changed(job, JobState.FAILED, severity=Severity.ERROR, code=code, error=message)

    @staticmethod
    def _outcome(result: DownloadResult | None) -> dict[str, Any]:
        """The verification state and the details of how a run ended, ready to store."""
        if result is None:
            return {}
        report = result.integrity
        details: dict[str, Any] = {"notes": list(result.notes)}
        if result.output is not None:
            details["processing"] = result.output.processing.value
            details["metadata"] = list(result.output.metadata)
        if report is not None:
            details["integrity"] = report.to_dict()
        return {
            "verification": (report.status if report else VerificationStatus.NOT_REQUESTED).value,
            "result_json": json.dumps(details),
        }

    def _end_attempt(
        self, attempt_id: int | None, outcome: str, code: str | None, message: str | None
    ) -> None:
        if attempt_id is not None:
            with contextlib.suppress(Exception):
                self._repo.end_attempt(attempt_id, outcome, code, message)

    def _changed(
        self,
        job: JobRecord,
        new: JobState,
        *,
        severity: Severity = Severity.INFO,
        **details: Any,
    ) -> None:
        self._bus.emit(
            "queue.job_state_changed",
            category=EventCategory.QUEUE,
            severity=severity,
            job_id=job.id,
            old=job.state.value,
            new=new.value,
            **details,
        )
        if new.is_terminal:
            self._bus.emit(
                f"queue.job_{new.value}",
                category=EventCategory.QUEUE,
                severity=severity,
                job_id=job.id,
                **details,
            )
        with self._cond:
            self._cond.notify_all()
