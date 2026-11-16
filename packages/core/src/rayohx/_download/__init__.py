"""The download engine, internal: the parts ``rayohx.downloader`` uses to run a download.

``MediaDownload`` downloads one media playlist: it prepares everything (strategy, disk space,
working folder, resume state), runs the segment pipeline, and then commits the output or cleans up.
The underscore modules next to it are its parts. Nothing here is public API.

The names below are imported the first time they are used.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx._download._media import DownloadSummary, MediaDownload
    from rayohx._download._sinks import FileSink, OutputSink, StreamSink

_EXPORTS = {
    "DownloadSummary": "rayohx._download._media",
    "FileSink": "rayohx._download._sinks",
    "MediaDownload": "rayohx._download._media",
    "OutputSink": "rayohx._download._sinks",
    "StreamSink": "rayohx._download._sinks",
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
