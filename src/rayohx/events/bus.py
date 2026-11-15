"""Delivers events to listeners."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rayohx.events.download import DownloadEvent

logger = logging.getLogger(__name__)

EventListener = Callable[["DownloadEvent"], None]


class EventBus:
    """Delivers events to listeners. A listener that raises never stops the download."""

    def __init__(self) -> None:
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

    def emit(self, event: DownloadEvent) -> None:
        """Deliver ``event`` to every listener, in the order they subscribed."""
        with self._lock:
            listeners = tuple(self._listeners)
        for listener in listeners:
            try:
                listener(event)
            except Exception:
                logger.exception("An event listener failed on %s", event.type.value)
