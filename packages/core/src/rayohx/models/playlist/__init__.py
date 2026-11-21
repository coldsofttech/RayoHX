"""Playlists: a master playlist lists streams, a media playlist lists segments.

The names below are imported the first time they are used.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx.models.playlist.master import MasterPlaylist
    from rayohx.models.playlist.media import MediaPlaylist
    from rayohx.models.playlist.resolution import Resolution
    from rayohx.models.playlist.tracks import AudioTrack, SubtitleTrack, VideoTrack
    from rayohx.models.playlist.variant import Variant

    #: Either kind of playlist.
    Playlist = MasterPlaylist | MediaPlaylist

_EXPORTS = {
    "AudioTrack": "rayohx.models.playlist.tracks",
    "MasterPlaylist": "rayohx.models.playlist.master",
    "MediaPlaylist": "rayohx.models.playlist.media",
    "Resolution": "rayohx.models.playlist.resolution",
    "SubtitleTrack": "rayohx.models.playlist.tracks",
    "Variant": "rayohx.models.playlist.variant",
    "VideoTrack": "rayohx.models.playlist.tracks",
}


def __getattr__(name: str) -> Any:
    """Import a name the first time it is used."""
    if name == "Playlist":
        from rayohx.models.playlist.master import MasterPlaylist
        from rayohx.models.playlist.media import MediaPlaylist

        value: Any = MasterPlaylist | MediaPlaylist
    else:
        module = _EXPORTS.get(name)
        if module is None:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
        value = getattr(import_module(module), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})


__all__ = [
    "AudioTrack",
    "MasterPlaylist",
    "MediaPlaylist",
    "Playlist",
    "Resolution",
    "SubtitleTrack",
    "Variant",
    "VideoTrack",
]
