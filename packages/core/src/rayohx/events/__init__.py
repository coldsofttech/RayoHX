"""The download state machine and the event bus.

The engine never prints. It reports what happens through typed events, and every front end (command
line, API, desktop window) subscribes to the same stream. ``download`` holds the state machine and
the event type, and ``bus`` delivers events to listeners. Both are also available here, for example
``rayohx.events.EventBus``.

The names below are imported the first time they are used.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx.events.bus import EventBus, EventListener
    from rayohx.events.download import TRANSITIONS, DownloadEvent, DownloadStateMachine

_EXPORTS = {
    "EventBus": "rayohx.events.bus",
    "EventListener": "rayohx.events.bus",
    "TRANSITIONS": "rayohx.events.download",
    "DownloadEvent": "rayohx.events.download",
    "DownloadStateMachine": "rayohx.events.download",
}


def __getattr__(name: str) -> Any:
    """Import a name the first time it is used."""
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_EXPORTS})


__all__ = [
    "TRANSITIONS",
    "DownloadEvent",
    "DownloadStateMachine",
    "EventBus",
    "EventListener",
]
