"""HLS playlist parsing (RFC 8216).

The parser reads a playlist line by line. It recognises a playlist by its content, not by its
file name or address, resolves every address against the playlist's own address with RFC 3986
rules, and reports problems with the line number. Tags it does not know are skipped, so newer
playlists keep working. Features that would give wrong results if ignored (I-frame-only
playlists) are refused with ``UnsupportedPlaylistError``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from rayohx.models import Playlist

_UNSUPPORTED_TAGS = {
    "EXT-X-I-FRAMES-ONLY": "I-frame-only playlists",
}
_MEDIA_TAGS = frozenset({"EXTINF", "EXT-X-TARGETDURATION"})
_MASTER_TAGS = frozenset({"EXT-X-STREAM-INF", "EXT-X-MEDIA"})


def parse_playlist(text: str, uri: str, *, variables: Mapping[str, str] | None = None) -> Playlist:
    """Parse a master or media playlist fetched from ``uri``.

    Every address in the result is absolute, and playlist variables (``EXT-X-DEFINE``) are
    already replaced. ``variables`` are those of the master playlist, for a media playlist that
    imports them.

    Raises:
        InvalidPlaylistError: If the text is not a valid playlist.
        UnsupportedPlaylistError: If it is valid but uses something the engine cannot handle.
    """
    from rayohx.errors import InvalidPlaylistError, UnsupportedPlaylistError
    from rayohx.playlist._lines import numbered_lines, tag_name
    from rayohx.playlist._variables import apply_variables
    from rayohx.playlist.detect import HEADER

    lines = numbered_lines(text)
    if not lines or lines[0][1] != HEADER:
        raise InvalidPlaylistError(
            "This is not an HLS playlist: it does not start with #EXTM3U.",
            hint="Check that the address points to an .m3u8 playlist and not to a web page.",
        )
    lines, defined = apply_variables(lines, uri, variables)
    tags = {tag_name(content) for _, content in lines if content.startswith("#EXT")}
    for tag, description in _UNSUPPORTED_TAGS.items():
        if tag in tags:
            raise UnsupportedPlaylistError(
                f"This playlist uses {description}, which is not supported."
            )
    is_media = bool(tags & _MEDIA_TAGS)
    if is_media and "EXT-X-STREAM-INF" in tags:
        raise InvalidPlaylistError("The playlist mixes master and media playlist tags.")
    if is_media:
        from rayohx.playlist._media import parse_media

        return parse_media(lines, uri)
    if tags & _MASTER_TAGS:
        from dataclasses import replace

        from rayohx.playlist._master import parse_master

        return replace(parse_master(lines, uri), variables=defined)
    raise InvalidPlaylistError(
        "The playlist has neither streams nor segments.",
        hint="A playlist needs #EXT-X-STREAM-INF or #EXTINF entries.",
    )
