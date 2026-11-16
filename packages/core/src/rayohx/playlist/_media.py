"""Reading media playlists."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rayohx.errors import InvalidPlaylistError
from rayohx.playlist._lines import tag_name, tag_value
from rayohx.playlist._values import byte_range, date_time, resolve, whole_tag_number

if TYPE_CHECKING:
    from datetime import datetime

    from rayohx.enums import ContainerFormat
    from rayohx.models import EncryptionInfo, InitMap, MediaPlaylist, Segment, SegmentRange
    from rayohx.playlist._lines import Line

_EXTINF = re.compile(r"^(\d+(?:\.\d+)?|\.\d+)\s*(?:,(.*))?$")

_FMP4_SUFFIXES = (".m4s", ".mp4", ".m4v", ".m4a", ".cmfv", ".cmfa", ".cmft")
_TS_SUFFIXES = (".ts", ".tsv", ".tsa")
_VTT_SUFFIXES = (".vtt", ".webvtt")


def parse_media(lines: list[Line], base: str) -> MediaPlaylist:
    from rayohx.models import MediaPlaylist, Segment, SegmentRange

    segments: list[Segment] = []
    target_duration: float | None = None
    media_sequence = 0
    end_list = False
    version: int | None = None
    playlist_type: str | None = None

    key: EncryptionInfo | None = None
    init_map: InitMap | None = None
    next_offsets: dict[str, int] = {}

    duration: float | None = None
    title = ""
    pending_range: SegmentRange | None = None
    discontinuity = False
    program_date_time: datetime | None = None
    extinf_line = 0

    for number, content in lines[1:]:
        if not content.startswith("#"):
            if duration is None:
                raise InvalidPlaylistError(
                    "A segment address has no #EXTINF before it.", line=number
                )
            uri = resolve(base, content, number)
            segment_range = None
            if pending_range is not None:
                offset = pending_range.offset
                if offset is None:
                    offset = next_offsets.get(uri)
                    if offset is None:
                        raise InvalidPlaylistError(
                            "A byte range without an offset must follow a range of the same file.",
                            line=number,
                        )
                segment_range = SegmentRange(pending_range.length, offset)
                next_offsets[uri] = offset + segment_range.length
            segments.append(
                Segment(
                    index=len(segments),
                    uri=uri,
                    duration=duration,
                    sequence_number=media_sequence + len(segments),
                    byte_range=segment_range,
                    init_map=init_map,
                    encryption=key,
                    discontinuity=discontinuity,
                    program_date_time=program_date_time,
                    title=title,
                )
            )
            duration, title, pending_range = None, "", None
            discontinuity, program_date_time = False, None
            continue
        if not content.startswith("#EXT"):
            continue  # a comment
        name = tag_name(content)
        if name == "EXTINF":
            if duration is not None:
                raise InvalidPlaylistError(
                    f"#EXTINF on line {extinf_line} has no segment address.", line=number
                )
            match = _EXTINF.match(tag_value(content).strip())
            if not match:
                raise InvalidPlaylistError("#EXTINF needs a duration.", line=number)
            duration = float(match.group(1))
            title = (match.group(2) or "").strip()
            extinf_line = number
        elif name == "EXT-X-TARGETDURATION":
            target_duration = float(whole_tag_number(content, number))
        elif name == "EXT-X-MEDIA-SEQUENCE":
            media_sequence = whole_tag_number(content, number)
        elif name == "EXT-X-VERSION":
            version = whole_tag_number(content, number)
        elif name == "EXT-X-ENDLIST":
            end_list = True
        elif name == "EXT-X-PLAYLIST-TYPE":
            playlist_type = tag_value(content).strip()
            if playlist_type not in {"VOD", "EVENT"}:
                raise InvalidPlaylistError(f"Unknown playlist type {playlist_type!r}.", line=number)
        elif name == "EXT-X-DISCONTINUITY":
            discontinuity = True
        elif name == "EXT-X-BYTERANGE":
            pending_range = byte_range(tag_value(content), number)
        elif name == "EXT-X-PROGRAM-DATE-TIME":
            program_date_time = date_time(tag_value(content).strip(), number)
        elif name == "EXT-X-KEY":
            from rayohx.playlist._keys import read_key

            key = read_key(content, number, base)
        elif name == "EXT-X-MAP":
            from rayohx.playlist._keys import read_map

            init_map = read_map(content, number, base)

    if duration is not None:
        raise InvalidPlaylistError(f"#EXTINF on line {extinf_line} has no segment address.")
    if target_duration is None:
        raise InvalidPlaylistError("The playlist has no #EXT-X-TARGETDURATION.")

    return MediaPlaylist(
        uri=base,
        segments=tuple(segments),
        target_duration=target_duration,
        media_sequence=media_sequence,
        end_list=end_list,
        version=version,
        playlist_type=playlist_type,
        container=detect_container(tuple(segments)),
    )


def detect_container(segments: tuple[Segment, ...]) -> ContainerFormat:
    """Guess the segment format from the playlist alone. Unclear cases are left to the sniffer."""
    from urllib.parse import urlsplit

    from rayohx.enums import ContainerFormat

    if not segments:
        return ContainerFormat.UNKNOWN
    if any(segment.init_map is not None for segment in segments):
        return ContainerFormat.FMP4
    path = urlsplit(segments[0].uri).path.lower()
    if path.endswith(_FMP4_SUFFIXES):
        return ContainerFormat.FMP4
    if path.endswith(_TS_SUFFIXES):
        return ContainerFormat.MPEG_TS
    if path.endswith(_VTT_SUFFIXES):
        return ContainerFormat.WEBVTT
    return ContainerFormat.UNKNOWN
