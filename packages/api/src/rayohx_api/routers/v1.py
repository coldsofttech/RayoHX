"""Version 1 of the API, served under ``/api/v1``."""

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from rayohx import __version__
from rayohx.errors import RayoHXError
from rayohx.platform import JobRecord
from rayohx.playlist.inspection import inspect, inspect_text
from rayohx.serialization import playlist_to_dict
from rayohx.storage import clean_workspaces

from rayohx_api.auth import authenticate
from rayohx_api.build import DEFAULT_CONCURRENCY, download_config, network_config, sources
from rayohx_api.config import Settings, get_settings
from rayohx_api.defaults import without_secrets
from rayohx_api.schemas_v1 import (
    CleanedFolder,
    CleanRequest,
    CleanResponse,
    Defaults,
    DownloadCreate,
    EngineEvent,
    InspectRequest,
    InspectResponse,
    Job,
    JobList,
    Progress,
    SettingsView,
)
from rayohx_api.service import enqueue, output_name, rayo, reset_state, store

router = APIRouter(tags=["v1"], dependencies=[Depends(authenticate)])


__all__ = ["reset_state", "router"]


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
        output_path=output_name(record),
        output_size_bytes=record.output_size,
        error=record.error_message,
    )


def _find(job_id: str) -> JobRecord:
    record = rayo().queue.get(job_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such download.")
    return record


@router.post("/inspect", summary="Look at a playlist without downloading it")
async def inspect_playlist(
    body: InspectRequest, settings: Annotated[Settings, Depends(get_settings)]
) -> InspectResponse:
    try:
        address = sources(body)[0]
        if body.playlist_text is not None:
            playlist = inspect_text(body.playlist_text, address)
        else:
            network = network_config(body.network, local=settings.allow_local_paths)
            playlist = await asyncio.to_thread(inspect, address, network)
    except RayoHXError as exc:
        raise _problem(status.HTTP_422_UNPROCESSABLE_CONTENT, exc) from exc
    return InspectResponse(playlist=playlist_to_dict(playlist))


@router.get("/downloads", summary="List downloads, newest first")
async def list_downloads() -> JobList:
    return JobList(items=[to_job(r) for r in rayo().queue.list(newest_first=True)])


@router.post(
    "/downloads",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start one download for each address",
)
async def create_download(
    body: DownloadCreate, settings: Annotated[Settings, Depends(get_settings)]
) -> JobList:
    try:
        records = enqueue(body, settings)
    except RayoHXError as exc:
        raise _problem(status.HTTP_422_UNPROCESSABLE_CONTENT, exc) from exc
    return JobList(items=[to_job(r) for r in records])


@router.get("/downloads/{job_id}", summary="One download")
async def get_download(job_id: str) -> Job:
    return to_job(_find(job_id))


@router.post("/downloads/{job_id}/pause", summary="Pause a download")
async def pause_download(job_id: str) -> Job:
    _find(job_id)
    rayo().queue.pause(job_id)
    return to_job(_find(job_id))


@router.post("/downloads/{job_id}/resume", summary="Resume a paused download")
async def resume_download(job_id: str) -> Job:
    _find(job_id)
    rayo().queue.resume(job_id)
    return to_job(_find(job_id))


@router.post("/downloads/{job_id}/cancel", summary="Cancel a download")
async def cancel_download(job_id: str) -> Job:
    _find(job_id)
    rayo().queue.cancel(job_id)
    return to_job(_find(job_id))


@router.delete(
    "/downloads/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Forget a finished download",
)
async def remove_download(job_id: str) -> Response:
    record = _find(job_id)
    if record.state.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cancel the download before removing it.")
    rayo().queue.remove(job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/downloads/{job_id}/log", summary="What the engine reported, most recent last")
async def download_log(job_id: str) -> list[EngineEvent]:
    _find(job_id)
    events = rayo().event_store.query(job_id=job_id, limit=200, newest_first=True)
    log = []
    for event in reversed(events):
        engine_type = event.payload.get("engine_type")
        if event.type.startswith("download.") and engine_type:
            log.append(
                EngineEvent(
                    time=event.timestamp,
                    type=str(engine_type),
                    state=str(event.payload.get("state", "")),
                    message=event.payload.get("message"),
                    segment=event.payload.get("segment"),
                )
            )
    return log


@router.get("/downloads/{job_id}/events", summary="Follow a download as server-sent events")
async def download_events(job_id: str, request: Request) -> StreamingResponse:
    _find(job_id)

    async def stream() -> AsyncIterator[str]:
        last = ""
        while not await request.is_disconnected():
            record = rayo().queue.get(job_id)
            if record is None:
                return
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
    return SettingsView(
        download_dir=str(settings.download_dir),
        max_active_downloads=settings.max_active_downloads,
        allow_local_paths=settings.allow_local_paths,
        defaults_file=str(store().path),
        version=__version__,
        defaults=store().get(),
    )


@router.get("/settings", summary="Server settings and saved default options")
async def read_settings(settings: Annotated[Settings, Depends(get_settings)]) -> SettingsView:
    return _view(settings)


@router.put("/settings/defaults", summary="Replace the saved default options")
async def save_defaults(
    body: Defaults, settings: Annotated[Settings, Depends(get_settings)]
) -> SettingsView:
    """Only options that are set are saved. Proxy logins and passwords are never saved."""
    data = without_secrets(body.model_dump(exclude_unset=True))
    try:
        # Check the combination now, so a bad default is refused here and not on every download.
        trial = DownloadCreate.model_validate({"url": "https://example.com/a.m3u8", **data})
        download_config(
            trial,
            base=settings.download_dir,
            local=settings.allow_local_paths,
            concurrency=DEFAULT_CONCURRENCY,
        )
        store().set(data)
    except RayoHXError as exc:
        raise _problem(status.HTTP_422_UNPROCESSABLE_CONTENT, exc) from exc
    except OSError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not save.") from exc
    return _view(settings)


@router.post("/clean", summary="Remove working folders left by interrupted downloads")
async def clean(
    body: CleanRequest, settings: Annotated[Settings, Depends(get_settings)]
) -> CleanResponse:
    """Only looks inside the download folder. Folders of running downloads are never removed."""
    removed, skipped = clean_workspaces(
        settings.download_dir, older_than_days=body.older_than_days, dry_run=body.dry_run
    )
    found = [
        CleanedFolder(name=info.name, size_bytes=info.size_bytes, age_days=round(info.age_days, 2))
        for info in removed
    ]
    return CleanResponse(
        dry_run=body.dry_run,
        folders=found,
        freed_bytes=sum(f.size_bytes for f in found),
        skipped_in_use=skipped,
    )
