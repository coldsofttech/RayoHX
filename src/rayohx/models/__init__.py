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

Every model is also available here, for example ``rayohx.models.SegmentRange``.
"""

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
