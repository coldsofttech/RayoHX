"""Choosing a variant and its audio and subtitle tracks.

Selection is a pure function of the playlist and the settings: the same input always gives the
same answer. Whenever a wish cannot be met exactly, the closest sensible track is used and a note
explains why, so nothing is silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rayohx.config import SelectionConfig
    from rayohx.models import AudioTrack, MasterPlaylist, SubtitleTrack, Variant


@dataclass(frozen=True, slots=True, kw_only=True)
class StreamSelection:
    """The tracks to download. ``notes`` explain any fallback that was needed."""

    variant: Variant
    audio_tracks: tuple[AudioTrack, ...] = ()
    subtitle_tracks: tuple[SubtitleTrack, ...] = ()
    notes: tuple[str, ...] = ()


def select_stream(master: MasterPlaylist, config: SelectionConfig) -> StreamSelection:
    """Choose the variant, audio tracks and subtitle tracks for ``config``.

    Raises:
        PlaylistError: If the playlist has no variants.
    """
    from rayohx.stream._tracks import select_audio, select_subtitles
    from rayohx.stream.variants import select_variant

    notes: list[str] = []
    variant = select_variant(master.variants, config, notes)
    if config.video_only:
        notes.append(
            "Only the video stream is downloaded; separate audio and subtitles are skipped."
        )
        return StreamSelection(variant=variant, notes=tuple(notes))
    audio = select_audio(master, variant, config, notes)
    subtitles = select_subtitles(master, variant, config, notes)
    return StreamSelection(
        variant=variant,
        audio_tracks=audio,
        subtitle_tracks=subtitles,
        notes=tuple(notes),
    )
