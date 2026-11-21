"""Reading a stream's playlists and checking what can be downloaded."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from rayohx._http import HttpClient
    from rayohx.enums import ContainerFormat
    from rayohx.models import MasterPlaylist, MediaPlaylist, SegmentData
    from rayohx.stream import StreamSelection


def kind(playlist: MasterPlaylist | MediaPlaylist) -> str:
    from rayohx.models import MasterPlaylist

    return "master" if isinstance(playlist, MasterPlaylist) else "media"


def describe(stream: StreamSelection) -> dict[str, object]:
    variant = stream.variant
    return {
        "bandwidth": variant.bandwidth,
        "resolution": str(variant.resolution) if variant.resolution else None,
        "codecs": list(variant.codecs),
        "audio": [track.name for track in stream.audio_tracks],
        "subtitles": [track.name for track in stream.subtitle_tracks],
        "notes": list(stream.notes),
    }


def load_media(
    client: HttpClient, url: str, variables: Mapping[str, str] | None = None
) -> MediaPlaylist:
    from rayohx.errors import InvalidPlaylistError
    from rayohx.models import MediaPlaylist
    from rayohx.playlist import is_hls_playlist, parse_playlist

    text, final = client.fetch_text(url)
    if not is_hls_playlist(text):
        raise InvalidPlaylistError(
            "A stream's address did not return an HLS playlist.",
            hint="The link may have expired or need sign-in.",
        )
    playlist = parse_playlist(text, final, variables=variables)
    if not isinstance(playlist, MediaPlaylist):
        raise InvalidPlaylistError("Expected a playlist of segments but found a list of streams.")
    return playlist


def require_single_stream(stream: StreamSelection | None) -> None:
    """Refuse streams whose tracks would have to be merged, which needs the muxer."""
    from rayohx.errors import OutputFormatError

    if stream is None:
        return
    if stream.audio_tracks:
        names = ", ".join(repr(track.name) for track in stream.audio_tracks)
        raise OutputFormatError(
            f"This stream keeps its audio in a separate track ({names}), which has to be merged "
            "with the video. Merging is not available yet.",
            hint="Set video_only to download the video without that audio.",
        )
    if stream.subtitle_tracks:
        raise OutputFormatError(
            "Saving subtitles is not available yet.",
            hint="Leave subtitles out, or set video_only.",
        )


def first_segment(client: HttpClient, media: MediaPlaylist) -> SegmentData:
    from rayohx._download._fetcher import HlsSegmentFetcher

    return HlsSegmentFetcher(client, media.segments).fetch(0)


def probe_container(client: HttpClient, media: MediaPlaylist) -> ContainerFormat:
    """Tell the segment format from the first segment when the playlist does not say."""
    from rayohx._download._containers import sniff_container
    from rayohx.enums import ContainerFormat

    if not media.segments:
        return ContainerFormat.UNKNOWN
    return sniff_container(first_segment(client, media).media)


def audio_codecs(
    client: HttpClient, media: MediaPlaylist, container: ContainerFormat
) -> tuple[str, ...]:
    """The audio codecs in a transport stream. Fragmented MP4 needs no fix, so it has none."""
    from rayohx._mux._source import probe_streams
    from rayohx.enums import ContainerFormat

    if container is not ContainerFormat.MPEG_TS:
        return ()
    streams = probe_streams(first_segment(client, media).media)
    return tuple(info.codec for info in streams if info.kind == "audio")
