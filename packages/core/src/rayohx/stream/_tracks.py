"""Choosing audio and subtitle tracks."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from rayohx.config.selection import ALL_TRACKS

if TYPE_CHECKING:
    from collections.abc import Sequence

    from rayohx.config import SelectionConfig
    from rayohx.models import AudioTrack, MasterPlaylist, SubtitleTrack, Variant

Track = TypeVar("Track", "AudioTrack", "SubtitleTrack")


def _normalise(language: str) -> str:
    return language.strip().lower().replace("_", "-")


def _language_matches(requested: str, available: str | None) -> int:
    """0 for no match, 2 for an exact match, 1 when only the main language agrees."""
    if not available:
        return 0
    wanted, offered = _normalise(requested), _normalise(available)
    if wanted == offered:
        return 2
    if wanted.partition("-")[0] == offered.partition("-")[0] and (
        "-" not in wanted or "-" not in offered
    ):
        return 1
    return 0


def _track_order(entry: tuple[int, Track]) -> tuple[bool, bool, bool, int]:
    index, track = entry
    return (track.forced, not track.default, not track.autoselect, index)


def _by_language(tracks: Sequence[Track], language: str) -> Track | None:
    scored = [
        (_language_matches(language, track.language), entry)
        for entry in enumerate(tracks)
        for track in [entry[1]]
    ]
    best_score = max((score for score, _ in scored), default=0)
    if best_score == 0:
        return None
    return min((entry for score, entry in scored if score == best_score), key=_track_order)[1]


def _by_name(tracks: Sequence[Track], name: str) -> Track | None:
    wanted = name.strip().lower()
    matches = [entry for entry in enumerate(tracks) if entry[1].name.lower() == wanted]
    return min(matches, key=_track_order)[1] if matches else None


def _default_track(tracks: Sequence[Track]) -> Track | None:
    return min(enumerate(tracks), key=_track_order)[1] if tracks else None


def _choose(
    tracks: Sequence[Track],
    languages: Sequence[str],
    names: Sequence[str],
    kind: str,
    notes: list[str],
) -> list[Track]:
    chosen: list[Track] = []
    if ALL_TRACKS in languages:
        return list(tracks)
    for name in names:
        track = _by_name(tracks, name)
        if track is None:
            notes.append(f"No {kind} track is named {name!r}.")
        elif track not in chosen:
            chosen.append(track)
    for language in languages:
        track = _by_language(tracks, language)
        if track is None:
            notes.append(f"No {kind} track is available in {language!r}.")
        elif track not in chosen:
            chosen.append(track)
    return chosen


def select_audio(
    master: MasterPlaylist, variant: Variant, config: SelectionConfig, notes: list[str]
) -> tuple[AudioTrack, ...]:
    tracks = master.audio_group(variant.audio_group) if variant.audio_group else ()
    wanted = bool(config.audio_languages or config.audio_names)
    if not tracks:
        if wanted:
            notes.append("The stream has no separate audio tracks, so its built-in audio is used.")
        return ()
    chosen = _choose(tracks, config.audio_languages, config.audio_names, "audio", notes)
    if not chosen:
        default = _default_track(tracks)
        if wanted and default is not None:
            notes.append(f"Using the default audio track {default.name!r} instead.")
        chosen = [default] if default is not None else []
    # A track without its own address is already inside the video segments.
    return tuple(track for track in chosen if track.uri)


def select_subtitles(
    master: MasterPlaylist, variant: Variant, config: SelectionConfig, notes: list[str]
) -> tuple[SubtitleTrack, ...]:
    if not (config.subtitle_languages or config.subtitle_names):
        return ()
    tracks = master.subtitle_group(variant.subtitle_group) if variant.subtitle_group else ()
    if not tracks:
        notes.append("The stream has no subtitle tracks.")
        return ()
    chosen = _choose(tracks, config.subtitle_languages, config.subtitle_names, "subtitle", notes)
    return tuple(track for track in chosen if track.uri)
