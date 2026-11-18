"""A playlist of variants and the tracks that go with them."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from rayohx.models.playlist.extras import SessionData
    from rayohx.models.playlist.tracks.audio import AudioTrack
    from rayohx.models.playlist.tracks.subtitle import SubtitleTrack
    from rayohx.models.playlist.tracks.video import VideoTrack
    from rayohx.models.playlist.variant import Variant


@dataclass(frozen=True, slots=True, kw_only=True)
class MasterPlaylist:
    """A playlist of variants and the tracks that go with them."""

    uri: str
    variants: tuple[Variant, ...]
    video_tracks: tuple[VideoTrack, ...] = ()
    audio_tracks: tuple[AudioTrack, ...] = ()
    subtitle_tracks: tuple[SubtitleTrack, ...] = ()
    version: int | None = None
    #: Variables the playlist defined with ``EXT-X-DEFINE``. Media playlists may import them.
    variables: Mapping[str, str] = field(default_factory=dict, repr=False)
    #: Information the playlist gives about the stream (``EXT-X-SESSION-DATA``).
    session_data: tuple[SessionData, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "variables", MappingProxyType(dict(self.variables)))
        object.__setattr__(self, "variants", tuple(self.variants))
        object.__setattr__(self, "video_tracks", tuple(self.video_tracks))
        object.__setattr__(self, "audio_tracks", tuple(self.audio_tracks))
        object.__setattr__(self, "subtitle_tracks", tuple(self.subtitle_tracks))
        object.__setattr__(self, "session_data", tuple(self.session_data))

    def audio_group(self, group_id: str) -> tuple[AudioTrack, ...]:
        """The audio tracks of one group."""
        return tuple(track for track in self.audio_tracks if track.group_id == group_id)

    def subtitle_group(self, group_id: str) -> tuple[SubtitleTrack, ...]:
        """The subtitle tracks of one group."""
        return tuple(track for track in self.subtitle_tracks if track.group_id == group_id)
