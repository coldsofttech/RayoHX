"""State and helpers the ``/api/v1`` route modules share."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException

from rayohx_api.jobs import JobManager

if TYPE_CHECKING:
    from typing import Any

    from rayohx_api.jobs import JobRecord
    from rayohx_api.schemas.v1.downloads import Job
    from rayohx_api.store import Store


class Preferences:
    """Defaults a client can change while the API runs. Concurrency is saved in the store."""

    def __init__(self, store: Store | None = None) -> None:
        self._store = store
        self.concurrency = 4
        self.quality = "best"
        self.overwrite = False
        saved = store.get_pref("concurrency") if store else None
        if saved and saved.isdigit():
            self.concurrency = int(saved)

    def update(self, changes: dict[str, Any]) -> None:
        for name, value in changes.items():
            setattr(self, name, value)
        if self._store and "concurrency" in changes:
            self._store.set_pref("concurrency", str(self.concurrency))


@lru_cache
def _state() -> tuple[JobManager, Preferences]:
    from rayohx_api.config import get_settings
    from rayohx_api.store import Store

    settings = get_settings()
    store = Store(settings.db_path)
    jobs = JobManager(settings.download_dir, settings.max_active_downloads, store)
    return jobs, Preferences(store)


def reset_state() -> None:
    """Forget every job. Tests call this together with ``get_settings.cache_clear()``."""
    if _state.cache_info().currsize and (store := _state()[1]._store):
        store.close()
    _state.cache_clear()


def manager() -> JobManager:
    return _state()[0]


def prefs() -> Preferences:
    return _state()[1]


Jobs = Annotated[JobManager, Depends(manager)]


def problem(code: int, exc: Exception) -> HTTPException:
    detail = str(exc)
    hint = getattr(exc, "hint", None)
    return HTTPException(code, f"{detail} {hint}" if hint else detail)


def to_job(record: JobRecord) -> Job:
    from rayohx_api.schemas.v1.downloads import Job, Progress

    progress = Progress(**record.progress) if record.progress else None
    return Job(
        id=record.id,
        url=record.url,
        state=record.state.value,
        created_at=record.created_at,
        updated_at=record.updated_at,
        progress=progress,
        output_path=record.output_path,
        output_size_bytes=record.output_size,
        error=record.error,
        quality=record.quality,
        retryable=record.retryable,
    )


def find_job(jobs: JobManager, job_id: str) -> JobRecord:
    from fastapi import status

    record = jobs.get(job_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such download.")
    return record
