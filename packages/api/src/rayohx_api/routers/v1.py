"""Version 1 of the API, served under ``/api/v1``."""

import asyncio
import re
import shutil
import time
from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from rayohx import __version__
from rayohx._download._workspace import FOLDER_PREFIX, LOCK_FILE, STATE_FILE, _FileLock
from rayohx.config import NetworkConfig
from rayohx.errors import RayoHXError
from rayohx.playlist.inspection import inspect
from rayohx.serialization import playlist_to_dict

from rayohx_api.auth import authenticate
from rayohx_api.config import Settings, get_settings
from rayohx_api.jobs import JobManager, JobRecord, UnsafeFilenameError
from rayohx_api.schemas_v1 import (
    CleanedFolder,
    CleanRequest,
    CleanResponse,
    DownloadCreate,
    InspectRequest,
    InspectResponse,
    Job,
    JobList,
    Progress,
    SettingsUpdate,
    SettingsView,
)

router = APIRouter(tags=["v1"], dependencies=[Depends(authenticate)])
DAY = 86400


class Preferences:
    """Defaults a client can change while the API runs. They are not saved to disk."""

    def __init__(self) -> None:
        self.concurrency = 4
        self.quality = "best"
        self.overwrite = False


@lru_cache
def _state() -> tuple[JobManager, Preferences]:
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


def _problem(code: int, exc: Exception) -> HTTPException:
    detail = str(exc)
    hint = getattr(exc, "hint", None)
    return HTTPException(code, f"{detail} {hint}" if hint else detail)


def to_job(record: JobRecord) -> Job:
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


def _find(jobs: JobManager, job_id: str) -> JobRecord:
    record = jobs.get(job_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such download.")
    return record


@router.post("/inspect", summary="Look at a playlist without downloading it")
async def inspect_playlist(body: InspectRequest) -> InspectResponse:
    network = NetworkConfig(headers=dict(body.network.headers))
    try:
        playlist = await asyncio.to_thread(inspect, body.url, network)
    except RayoHXError as exc:
        raise _problem(status.HTTP_422_UNPROCESSABLE_CONTENT, exc) from exc
    return InspectResponse(playlist=playlist_to_dict(playlist))


@router.get("/downloads", summary="List downloads, newest first")
async def list_downloads(jobs: Jobs) -> JobList:
    return JobList(items=[to_job(r) for r in jobs.list()])


@router.post("/downloads", status_code=status.HTTP_202_ACCEPTED, summary="Start a download")
async def create_download(body: DownloadCreate, jobs: Jobs) -> Job:
    try:
        record = jobs.create(body, concurrency=prefs().concurrency)
    except UnsafeFilenameError as exc:
        raise _problem(status.HTTP_422_UNPROCESSABLE_CONTENT, exc) from exc
    except RayoHXError as exc:
        raise _problem(status.HTTP_422_UNPROCESSABLE_CONTENT, exc) from exc
    return to_job(record)


@router.get("/downloads/{job_id}", summary="One download")
async def get_download(job_id: str, jobs: Jobs) -> Job:
    return to_job(_find(jobs, job_id))


@router.post("/downloads/{job_id}/pause", summary="Pause a download")
async def pause_download(job_id: str, jobs: Jobs) -> Job:
    record = _find(jobs, job_id)
    jobs.pause(record)
    return to_job(record)


@router.post("/downloads/{job_id}/resume", summary="Resume a paused download")
async def resume_download(job_id: str, jobs: Jobs) -> Job:
    record = _find(jobs, job_id)
    jobs.resume(record)
    return to_job(record)


@router.post("/downloads/{job_id}/cancel", summary="Cancel a download")
async def cancel_download(job_id: str, jobs: Jobs) -> Job:
    record = _find(jobs, job_id)
    jobs.cancel(record)
    return to_job(record)


@router.delete(
    "/downloads/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Forget a finished download",
)
async def remove_download(job_id: str, jobs: Jobs) -> Response:
    record = _find(jobs, job_id)
    if not jobs.remove(record):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cancel the download before removing it.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/downloads/{job_id}/events", summary="Follow a download as server-sent events")
async def download_events(job_id: str, request: Request, jobs: Jobs) -> StreamingResponse:
    record = _find(jobs, job_id)

    async def stream() -> AsyncIterator[str]:
        last = ""
        while not await request.is_disconnected():
            payload = to_job(record).model_dump_json()
            if payload != last:
                last = payload
                yield f"event: job\ndata: {payload}\n\n"
            if record.state.is_terminal:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def _view(settings: Settings) -> SettingsView:
    p = prefs()
    return SettingsView(
        download_dir=str(settings.download_dir),
        max_active_downloads=settings.max_active_downloads,
        concurrency=p.concurrency,
        quality=p.quality,
        overwrite=p.overwrite,
        version=__version__,
    )


@router.get("/settings", summary="Current defaults")
async def read_settings(settings: Annotated[Settings, Depends(get_settings)]) -> SettingsView:
    return _view(settings)


@router.patch("/settings", summary="Change defaults for this run")
async def update_settings(
    body: SettingsUpdate, settings: Annotated[Settings, Depends(get_settings)]
) -> SettingsView:
    p = prefs()
    for name, value in body.model_dump(exclude_none=True).items():
        setattr(p, name, value)
    return _view(settings)


_KEY_FOLDER = re.compile(r"^[0-9a-f]{16}$")


def _workspaces(folder: Path) -> list[Path]:
    try:
        children = sorted(folder.iterdir())
    except OSError:
        return []
    found = []
    for child in children:
        if child.is_symlink() or not child.is_dir():
            continue
        if child.name.startswith(FOLDER_PREFIX) or (
            _KEY_FOLDER.match(child.name) and (child / STATE_FILE).is_file()
        ):
            found.append(child)
    return found


def _in_use(folder: Path) -> bool:
    lock = folder / LOCK_FILE
    if not lock.is_file():
        return False
    probe = _FileLock(lock)
    if probe.acquire():
        probe.release()
        return False
    return True


@router.post("/clean", summary="Remove working folders left by interrupted downloads")
async def clean(
    body: CleanRequest, settings: Annotated[Settings, Depends(get_settings)]
) -> CleanResponse:
    """Only looks inside the download folder. Folders of running downloads are never removed."""
    now = time.time()
    found: list[CleanedFolder] = []
    skipped = 0
    for workspace in _workspaces(settings.download_dir):
        if _in_use(workspace):
            skipped += 1
            continue
        state = workspace / STATE_FILE
        used = (state if state.is_file() else workspace).stat().st_mtime
        age = (now - used) / DAY
        if age < body.older_than_days:
            continue
        size = sum(f.stat().st_size for f in workspace.rglob("*") if f.is_file())
        found.append(CleanedFolder(name=workspace.name, size_bytes=size, age_days=round(age, 2)))
        if not body.dry_run:
            shutil.rmtree(workspace, ignore_errors=True)
    return CleanResponse(
        dry_run=body.dry_run,
        folders=found,
        freed_bytes=sum(f.size_bytes for f in found),
        skipped_in_use=skipped,
    )
