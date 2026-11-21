"""Reading master playlists."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rayohx.models import AudioTrack, MasterPlaylist, SubtitleTrack, Variant, VideoTrack
    from rayohx.playlist._lines import Line


def parse_master(lines: list[Line], base: str) -> MasterPlaylist:
    from rayohx.errors import InvalidPlaylistError
    from rayohx.models import MasterPlaylist
    from rayohx.playlist._lines import is_comment, tag_name, tag_value
    from rayohx.playlist._values import resolve, whole_tag_number
    from rayohx.playlist.attributes import parse_attribute_list

    variants: list[Variant] = []
    video: list[VideoTrack] = []
    audio: list[AudioTrack] = []
    subtitles: list[SubtitleTrack] = []
    version: int | None = None

    index = 1
    while index < len(lines):
        number, content = lines[index]
        index += 1
        name = tag_name(content) if content.startswith("#EXT") else ""
        if name == "EXT-X-VERSION":
            version = whole_tag_number(content, number)
        elif name == "EXT-X-MEDIA":
            read_media_tag(content, number, base, video, audio, subtitles)
        elif name == "EXT-X-STREAM-INF":
            # Comments may sit between the tag and the address; another tag may not.
            while index < len(lines) and is_comment(lines[index][1]):
                index += 1
            if index >= len(lines) or lines[index][1].startswith("#"):
                raise InvalidPlaylistError(
                    "EXT-X-STREAM-INF must be followed by the stream's address.", line=number
                )
            uri_number, uri = lines[index]
            index += 1
            attributes = parse_attribute_list(tag_value(content), line=number)
            variants.append(variant(attributes, resolve(base, uri, uri_number), number))
    return MasterPlaylist(
        uri=base,
        variants=tuple(variants),
        video_tracks=tuple(video),
        audio_tracks=tuple(audio),
        subtitle_tracks=tuple(subtitles),
        version=version,
    )


def variant(attributes: dict[str, str], uri: str, line: int) -> Variant:
    from rayohx.models import Variant
    from rayohx.playlist._values import decimal, integer, resolution, split_list

    bandwidth = integer(attributes, "BANDWIDTH", line, required=True)
    assert bandwidth is not None  # noqa: S101 - required=True guarantees a value
    return Variant(
        uri=uri,
        bandwidth=bandwidth,
        average_bandwidth=integer(attributes, "AVERAGE-BANDWIDTH", line),
        resolution=resolution(attributes, line),
        codecs=split_list(attributes.get("CODECS")),
        frame_rate=decimal(attributes, "FRAME-RATE", line),
        video_range=attributes.get("VIDEO-RANGE"),
        video_group=attributes.get("VIDEO"),
        audio_group=attributes.get("AUDIO"),
        subtitle_group=attributes.get("SUBTITLES"),
        name=attributes.get("NAME"),
    )


def read_media_tag(
    content: str,
    line: int,
    base: str,
    video: list[VideoTrack],
    audio: list[AudioTrack],
    subtitles: list[SubtitleTrack],
) -> None:
    from rayohx.errors import InvalidPlaylistError
    from rayohx.models import AudioTrack, SubtitleTrack, VideoTrack
    from rayohx.playlist._lines import tag_value
    from rayohx.playlist._values import resolve, split_list
    from rayohx.playlist.attributes import parse_attribute_list

    attributes = parse_attribute_list(tag_value(content), line=line)
    kind = attributes.get("TYPE")
    if kind is None:
        raise InvalidPlaylistError("EXT-X-MEDIA needs a TYPE.", line=line)
    if kind == "CLOSED-CAPTIONS":
        return  # carried inside the video, nothing to download
    group_id = attributes.get("GROUP-ID")
    name = attributes.get("NAME")
    if not group_id or name is None:
        raise InvalidPlaylistError("EXT-X-MEDIA needs GROUP-ID and NAME.", line=line)
    raw_uri = attributes.get("URI")
    uri = resolve(base, raw_uri, line) if raw_uri else None
    default = attributes.get("DEFAULT") == "YES"
    autoselect = attributes.get("AUTOSELECT") == "YES"
    forced = attributes.get("FORCED") == "YES"
    language = attributes.get("LANGUAGE")
    characteristics = split_list(attributes.get("CHARACTERISTICS"))
    if kind == "AUDIO":
        audio.append(
            AudioTrack(
                group_id=group_id,
                name=name,
                language=language,
                uri=uri,
                default=default,
                autoselect=autoselect,
                forced=forced,
                channels=attributes.get("CHANNELS"),
                characteristics=characteristics,
            )
        )
    elif kind == "SUBTITLES":
        subtitles.append(
            SubtitleTrack(
                group_id=group_id,
                name=name,
                language=language,
                uri=uri,
                default=default,
                autoselect=autoselect,
                forced=forced,
                characteristics=characteristics,
            )
        )
    elif kind == "VIDEO":
        video.append(
            VideoTrack(
                group_id=group_id, name=name, uri=uri, default=default, autoselect=autoselect
            )
        )
    else:
        raise InvalidPlaylistError(f"Unknown EXT-X-MEDIA TYPE {kind!r}.", line=line)
