"""Version 2 of the API, served under ``/api/v2``: the persistent queue and the event log."""

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from rayohx.capabilities import detect
from rayohx.enums import OutputFormat
from rayohx.errors import RayoHXError
from rayohx.media import check_compatibility, inspect_media
from rayohx.platform import JobRecord, JobState, QueuePriority, RetryPolicy
from rayohx.platform.errors import QueueError
from rayohx.platform.events import EventCategory
from rayohx.platform.profiles import DownloadProfile, validate

from rayohx_api.auth import authenticate
from rayohx_api.build import DEFAULT_CONCURRENCY, download_config
from rayohx_api.config import Settings, get_settings
from rayohx_api.routers.v1 import _problem, to_job
from rayohx_api.schemas_v1 import DownloadCreate
from rayohx_api.schemas_v2 import (
    Attempt,
    BulkOutcome,
    CapabilitiesOut,
    CompatibilityOut,
    EventList,
    JobDetail,
    MediaInfoRequest,
    MediaInfoResponse,
    MoveRequest,
    PlatformEvent,
    ProfileList,
    ProfileOut,
    QueueAction,
    QueueAdd,
    QueueJob,
    QueueList,
    QueueSettings,
    QueueStats,
    VerificationOut,
)
from rayohx_api.service import enqueue, rayo

MAX_ID = 2**63 - 1  # the largest id the database can hold

router = APIRouter(tags=["v2"], dependencies=[Depends(authenticate)])


def to_queue_job(record: JobRecord) -> QueueJob:
    return QueueJob(
        **to_job(record).model_dump(),
        profile=record.profile_id,
        priority=record.priority.name.lower(),  # type: ignore[arg-type]
        rank=record.rank,
        attempts=record.attempts,
        max_attempts=record.spec.retry.max_attempts,
        verification=record.verification.value,
        error_code=record.error_code,
        started_at=record.started_at,
        finished_at=record.finished_at,
        not_before=record.not_before,
        recovered=record.recovered,
        needs_credentials=record.needs_credentials,
        notes=list(record.result.get("notes", [])) if record.result else [],
    )


def _extra(body: QueueAdd) -> dict[str, Any]:
    """What the request set about verification, metadata and naming, as setting overrides."""
    extra: dict[str, Any] = {}
    verify = {
        "level": body.verify.level,
        "expected_checksum": body.verify.checksum,
    }
    metadata = body.metadata.model_dump()
    sections = {
        "verify": {k: v for k, v in verify.items() if v is not None},
        "metadata": {k: v for k, v in metadata.items() if v is not None},
        "output": {"name_template": body.name_template} if body.name_template else {},
    }
    for name, values in sections.items():
        if values:
            extra[name] = values
    return extra


def _stats() -> QueueStats:
    return QueueStats(**rayo().queue.stats())


def _find(job_id: str) -> JobRecord:
    record = rayo().queue.get(job_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such job.")
    return record


@router.get("/queue", summary="List queued jobs in the order they will run")
async def list_queue(
    state: Annotated[list[JobState] | None, Query(description="Only these states.")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    newest_first: bool = False,
) -> QueueList:
    jobs = rayo().queue.list(states=state, limit=limit, newest_first=newest_first)
    return QueueList(items=[to_queue_job(j) for j in jobs], stats=_stats())


@router.post(
    "/queue",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Add a job for each address",
)
async def add_to_queue(
    body: QueueAdd, settings: Annotated[Settings, Depends(get_settings)]
) -> QueueList:
    try:
        retry = RetryPolicy(**body.retry.model_dump()) if "retry" in body.model_fields_set else None
        jobs = enqueue(
            body,
            settings,
            priority=QueuePriority.parse(body.priority),
            retry=retry,
            profile=body.profile,
            platform=True,
            extra=_extra(body),
        )
    except ValueError as exc:  # an unknown priority or retry value
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except RayoHXError as exc:
        raise _problem(status.HTTP_422_UNPROCESSABLE_CONTENT, exc) from exc
    return QueueList(items=[to_queue_job(j) for j in jobs], stats=_stats())


@router.get("/queue/stats", summary="Counts by state and how many jobs run at once")
async def queue_stats() -> QueueStats:
    return _stats()


@router.put("/queue/settings", summary="Change how many jobs run at once")
async def change_queue_settings(body: QueueSettings) -> QueueStats:
    rayo().queue.max_active = body.max_active
    return _stats()


@router.post("/queue/actions", summary="Pause, resume, cancel, retry, remove or reorder jobs")
async def queue_action(body: QueueAction) -> BulkOutcome:
    queue = rayo().queue
    if body.action == "priority":
        if body.priority is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "The priority action needs a priority."
            )
        result = queue.set_priority(body.ids, body.priority)
    else:
        handlers = {
            "pause": queue.pause,
            "resume": queue.resume,
            "cancel": queue.cancel,
            "retry": queue.retry,
            "remove": queue.remove,
            "top": queue.move_to_top,
            "bottom": queue.move_to_bottom,
        }
        result = handlers[body.action](body.ids)
    return BulkOutcome(**result.to_dict())


@router.get("/queue/{job_id}", summary="One job, with every run it has had")
async def get_job(job_id: str) -> JobDetail:
    record = _find(job_id)
    history = [Attempt(**a) for a in rayo().queue.attempts(job_id)]
    return JobDetail(**to_queue_job(record).model_dump(), attempt_history=history)


@router.get("/queue/{job_id}/verification", summary="How a finished job was checked")
async def get_verification(job_id: str) -> VerificationOut:
    _find(job_id)
    report = rayo().queue.verification(job_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This job was not verified.")
    return VerificationOut(**report)


@router.post("/queue/{job_id}/move", summary="Put a job just before another")
async def move_job(job_id: str, body: MoveRequest) -> QueueJob:
    _find(job_id)
    try:
        record = rayo().queue.move_before(job_id, body.before)
    except QueueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, exc.message) from exc
    return to_queue_job(record)


@router.post("/media-info", summary="Everything a stream offers, and what saving it would need")
async def media_info(
    body: MediaInfoRequest, settings: Annotated[Settings, Depends(get_settings)]
) -> MediaInfoResponse:
    """Codecs, frame rate, tracks, size and metadata; whether a format can be made from it."""
    address = body.url or body.base_url
    if address is None or (body.playlist_text is not None and not body.base_url):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Give url, or playlist_text with base_url.",
        )
    try:
        probe_request = DownloadCreate(url=address, network=body.network, selection=body.selection)
        config = download_config(
            probe_request,
            base=settings.download_dir,
            local=settings.allow_local_paths,
            concurrency=DEFAULT_CONCURRENCY,
        )
        found = await asyncio.to_thread(
            inspect_media,
            address,
            network=config.network,
            selection=config.selection,
            playlist_text=body.playlist_text,
            probe=body.probe,
        )
    except RayoHXError as exc:
        raise _problem(status.HTTP_422_UNPROCESSABLE_CONTENT, exc) from exc
    notes = check_compatibility(found, OutputFormat(body.format))
    return MediaInfoResponse(
        media=found.to_dict(),
        compatibility=[CompatibilityOut(**n.to_dict()) for n in notes],  # type: ignore[arg-type]
    )


def _profile(profile: DownloadProfile, default_id: str | None) -> ProfileOut:
    problems = [
        f.message for f in validate(profile, detect(), machine_checks=True) if f.level == "error"
    ]
    return ProfileOut(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        builtin=profile.builtin,
        default=profile.id == default_id,
        options=dict(profile.options),
        max_attempts=profile.retry.max_attempts if profile.retry else None,
        naming=profile.naming,
        metadata=profile.metadata,
        verify=profile.verify,
        problems=problems,
    )


@router.get("/profiles", summary="The built-in and saved profiles")
async def list_profiles() -> ProfileList:
    default = rayo().profiles.default()
    default_id = default.id if default else None
    return ProfileList(items=[_profile(p, default_id) for p in rayo().profiles.list()])


@router.get("/profiles/{profile_id}", summary="One profile")
async def get_profile(profile_id: str) -> ProfileOut:
    profile = rayo().profiles.get(profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such profile.")
    default = rayo().profiles.default()
    return _profile(profile, default.id if default else None)


@router.get("/capabilities", summary="What this server can do beyond the built-in engine")
async def capabilities() -> CapabilitiesOut:
    caps = detect()
    return CapabilitiesOut(
        **caps.as_dict(), formats={fmt.value: caps.supports(fmt) for fmt in OutputFormat}
    )


def _event(event: "object") -> PlatformEvent:
    return PlatformEvent(**event.to_dict())  # type: ignore[attr-defined]


@router.get("/events", summary="The saved event log, oldest first")
async def list_events(
    after_id: Annotated[int, Query(ge=0, le=MAX_ID, description="Only events after this id.")] = 0,
    job_id: str | None = None,
    category: EventCategory | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> EventList:
    store = rayo().event_store
    events = store.query(job_id=job_id, category=category, after_id=after_id, limit=limit)
    return EventList(
        items=[_event(e) for e in events], last_id=events[-1].id or after_id if events else after_id
    )


@router.get(
    "/events/stream",
    summary="Follow the event log as server-sent events",
    # A stream that never ends cannot be described to, or fuzzed by, the contract tests.
    include_in_schema=False,
)
async def stream_events(
    request: Request,
    after_id: Annotated[int | None, Query(ge=0, le=MAX_ID)] = None,
    job_id: str | None = None,
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    """Starts after ``after_id`` or the ``Last-Event-ID`` header, else from now on."""
    store = rayo().event_store
    cursor = after_id
    if cursor is None and last_event_id and last_event_id.isdigit() and len(last_event_id) < 19:
        cursor = int(last_event_id)
    if cursor is None:
        cursor = store.last_id()

    async def stream() -> AsyncIterator[str]:
        position = cursor
        idle = 0
        while not await request.is_disconnected():
            events = await asyncio.to_thread(
                store.query, job_id=job_id, after_id=position, limit=200
            )
            for event in events:
                position = event.id or position
                body = _event(event).model_dump_json()
                yield f"id: {position}\nevent: platform\ndata: {body}\n\n"
            idle = 0 if events else idle + 1
            if idle and idle % 30 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
