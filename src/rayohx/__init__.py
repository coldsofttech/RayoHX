"""RayoHX: an HLS download engine. Front ends (command line, API, window) all use this package.

The names below are imported the first time they are used, so ``import rayohx`` stays fast and a
front end loads only the parts it needs.
"""

from __future__ import annotations

import logging
from importlib import import_module
from typing import TYPE_CHECKING, Any

__version__ = "0.1.0"

# A library must stay quiet until the application asks for logs.
logging.getLogger("rayohx").addHandler(logging.NullHandler())

if TYPE_CHECKING:
    from rayohx.cancellation import CancellationToken
    from rayohx.enums import (
        ContainerFormat,
        DownloadState,
        EncryptionMethod,
        EventType,
        OutputFormat,
        RemuxBackend,
        SegmentState,
        StorageStrategy,
    )
    from rayohx.logs import (
        configure_logging,
    )
    from rayohx.models import (
        AudioTrack,
        DownloadProgress,
        DownloadRequest,
        DownloadResult,
        EncryptionInfo,
        InitMap,
        MasterPlaylist,
        MediaPlaylist,
        OutputInfo,
        Playlist,
        Resolution,
        Segment,
        SegmentData,
        SegmentRange,
        StorageMetrics,
        SubtitleTrack,
        Variant,
        VideoTrack,
    )
    from rayohx.playlist import (
        PlaylistFetcher,
        inspect_playlist,
        is_hls_playlist,
        parse_playlist,
    )
    from rayohx.playlist.inspection import inspect
    from rayohx.stream import StreamSelection, select_stream

_SUBMODULES = frozenset(
    {
        "cancellation",
        "config",
        "errors",
        "events",
        "models",
        "playlist",
        "stream",
    }
)
_EXPORTS = {
    "AudioTrack": "rayohx.models",
    "CancellationToken": "rayohx.cancellation",
    "ContainerFormat": "rayohx.enums",
    "DownloadProgress": "rayohx.models",
    "DownloadRequest": "rayohx.models",
    "DownloadResult": "rayohx.models",
    "DownloadState": "rayohx.enums",
    "EncryptionInfo": "rayohx.models",
    "EncryptionMethod": "rayohx.enums",
    "EventType": "rayohx.enums",
    "InitMap": "rayohx.models",
    "MasterPlaylist": "rayohx.models",
    "MediaPlaylist": "rayohx.models",
    "OutputFormat": "rayohx.enums",
    "OutputInfo": "rayohx.models",
    "Playlist": "rayohx.models",
    "PlaylistFetcher": "rayohx.playlist",
    "RemuxBackend": "rayohx.enums",
    "Resolution": "rayohx.models",
    "Segment": "rayohx.models",
    "SegmentData": "rayohx.models",
    "SegmentRange": "rayohx.models",
    "SegmentState": "rayohx.enums",
    "StorageMetrics": "rayohx.models",
    "StorageStrategy": "rayohx.enums",
    "StreamSelection": "rayohx.stream",
    "SubtitleTrack": "rayohx.models",
    "Variant": "rayohx.models",
    "VideoTrack": "rayohx.models",
    "configure_logging": "rayohx.logs",
    "inspect": "rayohx.playlist.inspection",
    "inspect_playlist": "rayohx.playlist",
    "is_hls_playlist": "rayohx.playlist",
    "parse_playlist": "rayohx.playlist",
    "select_stream": "rayohx.stream",
}


def __getattr__(name: str) -> Any:
    """Import a public name the first time it is used."""
    if name in _SUBMODULES:
        value = import_module(f"{__name__}.{name}")
        globals()[name] = value
        return value
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_EXPORTS, *_SUBMODULES})


__all__ = [
    "AudioTrack",
    "CancellationToken",
    "ContainerFormat",
    "DownloadProgress",
    "DownloadRequest",
    "DownloadResult",
    "DownloadState",
    "EncryptionInfo",
    "EncryptionMethod",
    "EventType",
    "InitMap",
    "MasterPlaylist",
    "MediaPlaylist",
    "OutputFormat",
    "OutputInfo",
    "Playlist",
    "PlaylistFetcher",
    "RemuxBackend",
    "Resolution",
    "Segment",
    "SegmentData",
    "SegmentRange",
    "SegmentState",
    "StorageMetrics",
    "StorageStrategy",
    "StreamSelection",
    "SubtitleTrack",
    "Variant",
    "VideoTrack",
    "__version__",
    "configure_logging",
    "inspect",
    "inspect_playlist",
    "is_hls_playlist",
    "parse_playlist",
    "select_stream",
]
