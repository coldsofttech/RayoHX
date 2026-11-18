"""Delivering platform events to listeners, and saving the ones worth keeping."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from rayohx.enums import EventType
from rayohx.platform.events.model import EventCategory, PlatformEvent, Severity
from rayohx.redaction import redact_text

if TYPE_CHECKING:
    from rayohx.events import DownloadEvent
    from rayohx.platform.events.store import EventStore

logger = logging.getLogger(__name__)

EventListener = Callable[[PlatformEvent], None]


class EventBus:
    """Publishes events to listeners. A failing listener or a failing save never stops the rest."""

    def __init__(
        self, store: EventStore | None = None, *, persist_min_severity: Severity = Severity.INFO
    ) -> None:
        self._store = store
        self._persist_min = persist_min_severity
        self._listeners: list[EventListener] = []
        self._lock = threading.Lock()

    def subscribe(self, listener: EventListener) -> Callable[[], None]:
        """Add ``listener`` and return a function that removes it again."""
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def publish(self, event: PlatformEvent) -> PlatformEvent:
        """Save ``event`` (if it is important enough) and deliver it. Returns what was delivered."""
        if self._store is not None and event.severity >= self._persist_min:
            try:
                event = self._store.append(event)
            except Exception:
                logger.exception("Could not save the event %s.", event.type)
        with self._lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                logger.exception("An event listener failed on %s.", event.type)
        return event

    def emit(
        self,
        type: str,
        *,
        category: EventCategory = EventCategory.SYSTEM,
        severity: Severity = Severity.INFO,
        job_id: str | None = None,
        correlation_id: str | None = None,
        **payload: Any,
    ) -> PlatformEvent:
        """Build an event from keyword arguments and publish it."""
        return self.publish(
            PlatformEvent(
                type=type,
                category=category,
                severity=severity,
                job_id=job_id,
                correlation_id=correlation_id,
                payload=payload,
            )
        )

    def forward(
        self, event: DownloadEvent, *, job_id: str | None = None, correlation_id: str | None = None
    ) -> PlatformEvent:
        """Publish an engine event as a platform event."""
        return self.publish(
            from_download_event(event, job_id=job_id, correlation_id=correlation_id)
        )


_WARNING_EVENTS = frozenset({EventType.SEGMENT_FAILED, EventType.DOWNLOAD_PAUSED})
_ERROR_EVENTS = frozenset({EventType.DOWNLOAD_FAILED})
_DEBUG_EVENTS = frozenset(
    {EventType.DOWNLOAD_PROGRESS, EventType.SEGMENT_STARTED, EventType.SEGMENT_COMPLETED}
)


def from_download_event(
    event: DownloadEvent, *, job_id: str | None = None, correlation_id: str | None = None
) -> PlatformEvent:
    """Describe an engine event as a platform event.

    Per-segment events are ``DEBUG`` so the bus does not save thousands of them by default.
    """
    if event.type in _ERROR_EVENTS:
        severity = Severity.ERROR
    elif event.type in _WARNING_EVENTS:
        severity = Severity.WARNING
    elif event.type in _DEBUG_EVENTS:
        severity = Severity.DEBUG
    else:
        severity = Severity.INFO
    payload: dict[str, Any] = {"state": event.state.value}
    if event.message:
        payload["message"] = redact_text(event.message)
    if event.segment_index is not None:
        payload["segment"] = event.segment_index
    if event.data:
        payload["data"] = dict(event.data)
    if event.progress is not None and event.type is not EventType.DOWNLOAD_PROGRESS:
        payload["downloaded_bytes"] = event.progress.downloaded_bytes
    return PlatformEvent(
        type=f"download.{event.type.value.removeprefix('download_')}",
        category=EventCategory.DOWNLOAD,
        severity=severity,
        timestamp=event.timestamp,
        job_id=job_id or event.download_id,
        correlation_id=correlation_id,
        payload=payload,
    )
