"""Version 2 of the API, served under ``/api/v2``: the persistent queue and the event log."""

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from rayohx.errors import RayoHXError
from rayohx.platform import JobRecord, JobState, RetryPolicy
from rayohx.platform.errors import QueueError
from rayohx.platform.events import EventCategory

from rayohx_api.auth import authenticate
from rayohx_api.config import Settings, get_settings
from rayohx_api.routers.v1 import _problem, to_job
from rayohx_api.schemas_v2 import (
    Attempt,
    BulkOutcome,
    EventList,
    JobDetail,
    MoveRequest,
    PlatformEvent,
    QueueAction,
    QueueAdd,
    QueueJob,
    QueueList,
    QueueSettings,
    QueueStats,
)
from rayohx_api.service import enqueue, rayo

MAX_ID = 2**63 - 1  # the largest id the database can hold

router = APIRouter(tags=["v2"], dependencies=[Depends(authenticate)])


def to_queue_job(record: JobRecord) -> QueueJob:
    return QueueJob(
        **to_job(record).model_dump(),
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
    )


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
        retry = RetryPolicy(**body.retry.model_dump())
        request = body.model_copy(update={}, deep=True)
        jobs = enqueue(request, settings, priority=body.priority, retry=retry)  # type: ignore[arg-type]
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


@router.post("/queue/{job_id}/move", summary="Put a job just before another")
async def move_job(job_id: str, body: MoveRequest) -> QueueJob:
    _find(job_id)
    try:
        record = rayo().queue.move_before(job_id, body.before)
    except QueueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, exc.message) from exc
    return to_queue_job(record)


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
