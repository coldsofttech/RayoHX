"""State and helpers the ``/api/v1`` route modules share."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException

from rayohx_api.jobs import JobManager

if TYPE_CHECKING:
    from rayohx_api.jobs import JobRecord
    from rayohx_api.schemas.v1.downloads import Job


class Preferences:
    """Defaults a client can change while the API runs. They are not saved to disk."""

    def __init__(self) -> None:
        self.concurrency = 4
        self.quality = "best"
        self.overwrite = False


@lru_cache
def _state() -> tuple[JobManager, Preferences]:
    from rayohx_api.config import get_settings

    settings = get_settings()
    return JobManager(settings.download_dir, settings.max_active_downloads), Preferences()


def reset_state() -> None:
    """Forget every job. Tests call this together with ``get_settings.cache_clear()``."""
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
    )


def find_job(jobs: JobManager, job_id: str) -> JobRecord:
    from fastapi import status

    record = jobs.get(job_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such download.")
    return record
