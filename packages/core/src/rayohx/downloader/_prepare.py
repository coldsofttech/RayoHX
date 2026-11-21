"""The steps between inspecting a stream and downloading it: its audio and subtitle tracks and the
remuxer to use."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from rayohx._download._output import OutputPlan
    from rayohx._http import HttpClient
    from rayohx.config import DownloadConfig
    from rayohx.downloader._delivery import Rendition
    from rayohx.enums import ContainerFormat, EventType
    from rayohx.models import MediaPlaylist, SubtitleTrack
    from rayohx.stream import StreamSelection

    class Emit(Protocol):
        def __call__(self, kind: EventType, *, data: dict[str, object] | None = None) -> None: ...


logger = logging.getLogger(__name__)


def load_renditions(
    client: HttpClient,
    stream: StreamSelection | None,
    variables: Mapping[str, str] | None,
    emit: Emit,
) -> list[Rendition]:
    """Load the playlists of the separate audio tracks that have to be joined in."""
    from rayohx.downloader._delivery import Rendition
    from rayohx.downloader._stream import load_media, probe_container
    from rayohx.enums import ContainerFormat, EventType
    from rayohx.errors import OutputFormatError

    renditions = []
    for track in stream.audio_tracks if stream else ():
        assert track.uri is not None  # noqa: S101 - selection keeps only tracks with an address
        media = load_media(client, track.uri, variables)
        container = media.container
        if container is ContainerFormat.UNKNOWN:
            container = probe_container(client, media)
        if container not in {ContainerFormat.MPEG_TS, ContainerFormat.FMP4}:
            raise OutputFormatError(
                f"The audio track {track.name!r} is in a form that cannot be joined in.",
                hint="Only MPEG-TS and fragmented MP4 audio are supported.",
            )
        emit(EventType.PLAYLIST_LOADED, data={"kind": "media", "audio": track.name})
        renditions.append(Rendition(track, media, container))
    return renditions


def load_subtitle_jobs(
    client: HttpClient,
    stream: StreamSelection | None,
    plan: OutputPlan,
    variables: Mapping[str, str] | None,
    emit: Emit,
) -> list[tuple[SubtitleTrack, MediaPlaylist, Path]]:
    """Load the playlists of the subtitle tracks and decide where each is saved."""
    from rayohx.downloader._delivery import subtitle_path
    from rayohx.downloader._stream import load_media
    from rayohx.enums import ContainerFormat, EventType
    from rayohx.errors import OutputFormatError

    jobs = []
    used: set[Path] = set()
    for track in stream.subtitle_tracks if stream else ():
        assert track.uri is not None  # noqa: S101 - selection keeps only tracks with an address
        media = load_media(client, track.uri, variables)
        if media.container not in {ContainerFormat.WEBVTT, ContainerFormat.UNKNOWN}:
            raise OutputFormatError(
                f"The subtitles {track.name!r} are not WebVTT text, which is all that can "
                "be saved.",
                hint="Leave subtitles out, or set video_only.",
            )
        emit(EventType.PLAYLIST_LOADED, data={"kind": "media", "subtitles": track.name})
        jobs.append((track, media, subtitle_path(plan.path, track, used)))
    return jobs


def choose_backend(
    client: HttpClient,
    media: MediaPlaylist,
    container: ContainerFormat,
    audios: list[Rendition],
    plan: OutputPlan,
    config: DownloadConfig,
) -> Path | None:
    """Pick what re-wraps the stream: ``None`` for the built-in remuxer, else an FFmpeg."""
    from rayohx._mux._ffmpeg import find_ffmpeg
    from rayohx._mux._source import probe_codecs
    from rayohx.downloader._stream import first_segment
    from rayohx.enums import ContainerFormat, RemuxBackend
    from rayohx.errors import OutputFormatError, UnsupportedCodecError

    if not plan.mux:
        return None
    wanted = config.output.remux_backend
    executable = find_ffmpeg(config.output.ffmpeg_path)
    if wanted is RemuxBackend.FFMPEG:
        if executable is None:
            raise OutputFormatError(
                "FFmpeg was asked for but could not be found.",
                hint="FFmpeg is an optional prerequisite: install it, or set its path in "
                "the output settings.",
            )
        return executable
    inputs = [(media, container), *((audio.media, audio.container) for audio in audios)]
    try:
        for item, fmt in inputs:
            if fmt is ContainerFormat.MPEG_TS:
                probe_codecs(first_segment(client, item).media)
    except UnsupportedCodecError as exc:
        if wanted is RemuxBackend.AUTO and executable is not None:
            logger.info("Using FFmpeg because the stream uses %s.", exc.codec)
            return executable
        hint = (
            "Set the remux backend to auto and install FFmpeg, an optional prerequisite."
            if wanted is RemuxBackend.NATIVE
            else "FFmpeg is not installed. It is an optional prerequisite for streams like "
            "this: install it, or set its path in the output settings."
        )
        raise UnsupportedCodecError(exc.codec, hint=hint) from exc
    return None
