"""The segment download engine, internal for now: one media playlist from start to finish.

``MediaDownload`` prepares everything (strategy, disk space, working folder, resume state), runs
the segment pipeline, and then commits the output or cleans up. The parts it uses live in the
underscore modules next to it. A public ``download()`` will be added here when the controller
exists.

The names below are imported the first time they are used.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx.download._media import DownloadSummary, MediaDownload
    from rayohx.download._sinks import FileSink, OutputSink, StreamSink

_EXPORTS = {
    "DownloadSummary": "rayohx.download._media",
    "FileSink": "rayohx.download._sinks",
    "MediaDownload": "rayohx.download._media",
    "OutputSink": "rayohx.download._sinks",
    "StreamSink": "rayohx.download._sinks",
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
    "DownloadSummary",
    "FileSink",
    "MediaDownload",
    "OutputSink",
    "StreamSink",
]
