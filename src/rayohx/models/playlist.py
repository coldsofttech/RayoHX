"""Either kind of playlist."""

from rayohx.models.master_playlist import MasterPlaylist
from rayohx.models.media_playlist import MediaPlaylist

Playlist = MasterPlaylist | MediaPlaylist
