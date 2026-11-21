"""The renditions a master playlist offers next to its video streams.

The names below are imported the first time they are used.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx.models.playlist.tracks.audio import AudioTrack
    from rayohx.models.playlist.tracks.subtitle import SubtitleTrack
    from rayohx.models.playlist.tracks.video import VideoTrack

_EXPORTS = {
    "AudioTrack": "rayohx.models.playlist.tracks.audio",
    "SubtitleTrack": "rayohx.models.playlist.tracks.subtitle",
    "VideoTrack": "rayohx.models.playlist.tracks.video",
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
    "AudioTrack",
    "SubtitleTrack",
    "VideoTrack",
]
