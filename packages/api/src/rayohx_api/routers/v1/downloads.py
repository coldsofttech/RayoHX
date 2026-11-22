"""Start, follow and control downloads."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse

from rayohx_api.config import Settings, get_settings
from rayohx_api.routers.v1.deps import Jobs
from rayohx_api.schemas.v1.downloads import DownloadCreate, Job, JobList

router = APIRouter()


@router.get("/downloads", summary="List downloads, newest first")
async def list_downloads(jobs: Jobs) -> JobList:
    from rayohx_api.routers.v1.deps import to_job

    return JobList(items=[to_job(r) for r in jobs.all()])


@router.post(
    "/downloads",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start one download for each address",
)
async def create_download(
    body: DownloadCreate, jobs: Jobs, settings: Annotated[Settings, Depends(get_settings)]
) -> JobList:
    from rayohx.errors import RayoHXError

    from rayohx_api.jobs import UnsafeFilenameError
    from rayohx_api.routers.v1.deps import prefs, problem, to_job

    try:
        records = jobs.create(
            body, concurrency=prefs().concurrency, local_paths=settings.allow_local_paths
        )
    except (UnsafeFilenameError, RayoHXError) as exc:
        raise problem(status.HTTP_422_UNPROCESSABLE_CONTENT, exc) from exc
    return JobList(items=[to_job(r) for r in records])


@router.delete(
    "/downloads",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear the history of finished downloads",
)
async def clear_downloads(jobs: Jobs) -> Response:
    jobs.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/downloads/{job_id}", summary="One download")
async def get_download(job_id: str, jobs: Jobs) -> Job:
    from rayohx_api.routers.v1.deps import find_job, to_job

    return to_job(find_job(jobs, job_id))


@router.post("/downloads/{job_id}/pause", summary="Pause a download")
async def pause_download(job_id: str, jobs: Jobs) -> Job:
    from rayohx_api.routers.v1.deps import find_job, to_job

    record = find_job(jobs, job_id)
    jobs.pause(record)
    return to_job(record)


@router.post("/downloads/{job_id}/resume", summary="Resume a paused download")
async def resume_download(job_id: str, jobs: Jobs) -> Job:
    from rayohx_api.routers.v1.deps import find_job, to_job

    record = find_job(jobs, job_id)
    jobs.resume(record)
    return to_job(record)


@router.post("/downloads/{job_id}/retry", summary="Start a failed or cancelled download again")
async def retry_download(
    job_id: str, jobs: Jobs, settings: Annotated[Settings, Depends(get_settings)]
) -> Job:
    from fastapi import HTTPException
    from rayohx.errors import RayoHXError

    from rayohx_api.jobs import UnsafeFilenameError
    from rayohx_api.routers.v1.deps import find_job, prefs, problem, to_job

    record = find_job(jobs, job_id)
    try:
        started = jobs.retry(
            record, concurrency=prefs().concurrency, local_paths=settings.allow_local_paths
        )
    except (UnsafeFilenameError, RayoHXError) as exc:
        raise problem(status.HTTP_422_UNPROCESSABLE_CONTENT, exc) from exc
    if not started:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Only a failed or cancelled download can be retried."
        )
    return to_job(record)


@router.post("/downloads/{job_id}/cancel", summary="Cancel a download")
async def cancel_download(job_id: str, jobs: Jobs) -> Job:
    from rayohx_api.routers.v1.deps import find_job, to_job

    record = find_job(jobs, job_id)
    jobs.cancel(record)
    return to_job(record)


@router.delete(
    "/downloads/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Forget a finished download",
)
async def remove_download(job_id: str, jobs: Jobs) -> Response:
    from fastapi import HTTPException

    from rayohx_api.routers.v1.deps import find_job

    record = find_job(jobs, job_id)
    if not jobs.remove(record):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cancel the download before removing it.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/downloads/{job_id}/events", summary="Follow a download as server-sent events")
async def download_events(job_id: str, request: Request, jobs: Jobs) -> StreamingResponse:
    import asyncio
    from collections.abc import AsyncIterator

    from rayohx_api.routers.v1.deps import find_job, to_job

    record = find_job(jobs, job_id)

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
