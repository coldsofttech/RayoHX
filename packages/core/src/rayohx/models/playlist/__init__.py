"""Playlists: a master playlist lists streams, a media playlist lists segments."""

from rayohx.models.playlist.master import MasterPlaylist
from rayohx.models.playlist.media import MediaPlaylist
from rayohx.models.playlist.resolution import Resolution
from rayohx.models.playlist.tracks import AudioTrack, SubtitleTrack, VideoTrack
from rayohx.models.playlist.variant import Variant

#: Either kind of playlist.
Playlist = MasterPlaylist | MediaPlaylist

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
