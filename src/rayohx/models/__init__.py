"""Immutable domain models: playlists, tracks, segments, progress and results.

The models carry data and simple derived values only. Parsing, selecting and downloading live in
other modules, so any front end can use these types without pulling in the engine. Each model lives
in its own module, named after it in snake case (``segment_range`` holds ``SegmentRange``), and is
also available here, for example ``rayohx.models.SegmentRange``.
"""

from rayohx.models.audio_track import AudioTrack
from rayohx.models.download_progress import DownloadProgress
from rayohx.models.download_request import DownloadRequest
from rayohx.models.download_result import DownloadResult
from rayohx.models.encryption_info import EncryptionInfo
from rayohx.models.init_map import InitMap
from rayohx.models.master_playlist import MasterPlaylist
from rayohx.models.media_playlist import MediaPlaylist
from rayohx.models.output_info import OutputInfo
from rayohx.models.playlist import Playlist
from rayohx.models.resolution import Resolution
from rayohx.models.segment import Segment
from rayohx.models.segment_range import SegmentRange
from rayohx.models.storage_metrics import StorageMetrics
from rayohx.models.subtitle_track import SubtitleTrack
from rayohx.models.variant import Variant
from rayohx.models.video_track import VideoTrack

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
    "SegmentRange",
    "StorageMetrics",
    "SubtitleTrack",
    "Variant",
    "VideoTrack",
]
