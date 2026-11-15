"""The download state machine and the event bus.

The engine never prints. It reports what happens through typed events, and every front end (command
line, API, desktop window) subscribes to the same stream. ``download`` holds the state machine and
the event type, and ``bus`` delivers events to listeners. Both are also available here, for example
``rayohx.events.EventBus``.
"""

from rayohx.events.bus import EventBus, EventListener
from rayohx.events.download import TRANSITIONS, DownloadEvent, DownloadStateMachine

__all__ = [
    "TRANSITIONS",
    "DownloadEvent",
    "DownloadStateMachine",
    "EventBus",
    "EventListener",
]
