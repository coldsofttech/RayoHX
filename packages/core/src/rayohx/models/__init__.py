"""Immutable domain models: playlists, tracks, segments, progress and results.

The models carry data and simple derived values only. Parsing, selecting and downloading live in
other modules, so any front end can use these types without pulling in the engine. Each model lives
in its own module, named after it in snake case, and related models share a package:

- ``playlist`` holds ``MasterPlaylist``, ``MediaPlaylist``, ``Variant``, ``Resolution`` and the
  ``tracks`` (``AudioTrack``, ``SubtitleTrack``, ``VideoTrack``).
- ``segment`` holds ``Segment``, ``SegmentData``, ``SegmentRange``, ``EncryptionInfo`` and
  ``InitMap``.
- ``download`` holds ``DownloadRequest``, ``DownloadProgress``, ``DownloadResult``,
  ``StorageMetrics`` and ``OutputInfo``.

Every model is also available here, for example ``rayohx.models.SegmentRange``. The names are
imported the first time they are used.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx.models.download import (
        DownloadProgress,
        DownloadRequest,
        DownloadResult,
        OutputInfo,
        StorageMetrics,
    )
    from rayohx.models.playlist import (
        AudioTrack,
        MasterPlaylist,
        MediaPlaylist,
        Playlist,
        Resolution,
        SubtitleTrack,
        Variant,
        VideoTrack,
    )
    from rayohx.models.segment import (
        EncryptionInfo,
        InitMap,
        Segment,
        SegmentData,
        SegmentRange,
    )

#: The package each name comes from. Those packages load their own names the same way.
_EXPORTS = {
    "DownloadProgress": "rayohx.models.download",
    "DownloadRequest": "rayohx.models.download",
    "DownloadResult": "rayohx.models.download",
    "OutputInfo": "rayohx.models.download",
    "StorageMetrics": "rayohx.models.download",
    "AudioTrack": "rayohx.models.playlist",
    "MasterPlaylist": "rayohx.models.playlist",
    "MediaPlaylist": "rayohx.models.playlist",
    "Playlist": "rayohx.models.playlist",
    "Resolution": "rayohx.models.playlist",
    "SubtitleTrack": "rayohx.models.playlist",
    "Variant": "rayohx.models.playlist",
    "VideoTrack": "rayohx.models.playlist",
    "EncryptionInfo": "rayohx.models.segment",
    "InitMap": "rayohx.models.segment",
    "Segment": "rayohx.models.segment",
    "SegmentData": "rayohx.models.segment",
    "SegmentRange": "rayohx.models.segment",
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
    "DownloadProgress",
    "DownloadRequest",
    "DownloadResult",
    "EncryptionInfo",
    "InitMap",
    "MasterPlaylist",
    "MediaPlaylist",
    "OutputInfo",
    "Playlist",
    "Resolution",
    "Segment",
    "SegmentData",
    "SegmentRange",
    "StorageMetrics",
    "SubtitleTrack",
    "Variant",
    "VideoTrack",
]
