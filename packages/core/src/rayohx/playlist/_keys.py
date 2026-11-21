"""Reading encryption keys and initialization maps."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rayohx.models import EncryptionInfo, InitMap


def read_key(content: str, line: int, base: str) -> EncryptionInfo | None:
    from rayohx.enums import EncryptionMethod
    from rayohx.errors import InvalidPlaylistError, UnsupportedPlaylistError
    from rayohx.models import EncryptionInfo
    from rayohx.playlist._lines import tag_value
    from rayohx.playlist._values import resolve
    from rayohx.playlist.attributes import parse_attribute_list

    attributes = parse_attribute_list(tag_value(content), line=line)
    method_text = attributes.get("METHOD")
    if method_text is None:
        raise InvalidPlaylistError("EXT-X-KEY needs a METHOD.", line=line)
    try:
        method = EncryptionMethod(method_text)
    except ValueError:
        raise UnsupportedPlaylistError(
            f"The encryption method {method_text!r} is not supported (line {line})."
        ) from None
    if method is EncryptionMethod.NONE:
        return None
    raw_uri = attributes.get("URI")
    if not raw_uri:
        raise InvalidPlaylistError("An encrypted playlist's EXT-X-KEY needs a URI.", line=line)
    iv = None
    if "IV" in attributes:
        try:
            iv = EncryptionInfo.parse_iv(attributes["IV"])
        except InvalidPlaylistError as exc:
            raise InvalidPlaylistError(exc.message, line=line) from None
    return EncryptionInfo(
        method=method,
        uri=resolve(base, raw_uri, line, web_only=False),
        iv=iv,
        key_format=attributes.get("KEYFORMAT", "identity"),
        key_format_versions=attributes.get("KEYFORMATVERSIONS"),
    )


def read_map(content: str, line: int, base: str) -> InitMap:
    from rayohx.errors import InvalidPlaylistError
    from rayohx.models import InitMap
    from rayohx.playlist._lines import tag_value
    from rayohx.playlist._values import resolve
    from rayohx.playlist.attributes import parse_attribute_list

    attributes = parse_attribute_list(tag_value(content), line=line)
    raw_uri = attributes.get("URI")
    if not raw_uri:
        raise InvalidPlaylistError("EXT-X-MAP needs a URI.", line=line)
    range_ = None
    if "BYTERANGE" in attributes:
        from rayohx.models import SegmentRange
        from rayohx.playlist._values import byte_range

        parsed = byte_range(attributes["BYTERANGE"], line)
        range_ = SegmentRange(parsed.length, parsed.offset if parsed.offset is not None else 0)
    return InitMap(uri=resolve(base, raw_uri, line), byte_range=range_)
