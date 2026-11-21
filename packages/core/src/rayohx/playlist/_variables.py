"""Playlist variables: ``#EXT-X-DEFINE`` and ``{$name}`` references."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from rayohx.playlist._lines import Line

_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_REFERENCE = re.compile(r"\{\$([A-Za-z0-9_-]+)\}")
_DEFINE = "EXT-X-DEFINE"


def _raw_query(uri: str) -> dict[str, str]:
    """The query parameters of ``uri`` with their values as written (still percent-encoded)."""
    from urllib.parse import urlsplit

    found: dict[str, str] = {}
    for part in urlsplit(uri).query.split("&"):
        key, _, value = part.partition("=")
        if key:
            found[key] = value
    return found


def apply_variables(
    lines: list[Line], uri: str, imported: Mapping[str, str] | None = None
) -> tuple[list[Line], dict[str, str]]:
    """Read every ``EXT-X-DEFINE`` and replace each ``{$name}`` reference with its value.

    ``NAME``/``VALUE`` defines a variable, ``QUERYPARAM`` takes it from the playlist's own
    address, and ``IMPORT`` takes it from the master playlist (``imported``). The define lines
    are removed. Returns the new lines and the variables that were defined.

    Raises:
        InvalidPlaylistError: For a malformed define, a repeated name or an undefined reference.
        UnsupportedPlaylistError: For ``IMPORT`` when the master playlist's variables are not
            available.
    """
    from rayohx.errors import InvalidPlaylistError, UnsupportedPlaylistError
    from rayohx.playlist._lines import tag_name, tag_value
    from rayohx.playlist.attributes import parse_attribute_list

    variables: dict[str, str] = {}
    rest: list[Line] = []
    query: dict[str, str] | None = None
    for number, content in lines:
        if not (content.startswith("#EXT") and tag_name(content) == _DEFINE):
            rest.append((number, content))
            continue
        attributes = parse_attribute_list(tag_value(content), line=number)
        if "NAME" in attributes and "VALUE" in attributes:
            name, value = attributes["NAME"], attributes["VALUE"]
        elif "QUERYPARAM" in attributes:
            name = attributes["QUERYPARAM"]
            if query is None:
                query = _raw_query(uri)
            if name not in query:
                raise InvalidPlaylistError(
                    f"The address has no query parameter {name!r} (line {number}).", line=number
                )
            value = query[name]
        elif "IMPORT" in attributes:
            name = attributes["IMPORT"]
            if imported is None:
                raise UnsupportedPlaylistError(
                    f"This playlist imports the variable {name!r} from its master playlist "
                    f"(line {number}), which is not available here.",
                )
            if name not in imported:
                raise InvalidPlaylistError(
                    f"The master playlist does not define {name!r} (line {number}).", line=number
                )
            value = imported[name]
        else:
            raise InvalidPlaylistError(
                "EXT-X-DEFINE needs NAME and VALUE, QUERYPARAM or IMPORT.", line=number
            )
        if not _NAME.match(name):
            raise InvalidPlaylistError(f"{name!r} is not a valid variable name.", line=number)
        if name in variables:
            raise InvalidPlaylistError(f"The variable {name!r} is defined twice.", line=number)
        variables[name] = value
    if not any("{$" in content for _, content in rest):
        return rest, variables

    substituted: list[Line] = []
    for number, content in rest:

        def lookup(match: re.Match[str], number: int = number) -> str:
            name = match[1]
            if name not in variables:
                raise InvalidPlaylistError(
                    f"The variable {name!r} is used but not defined (line {number}).",
                    line=number,
                )
            return variables[name]

        substituted.append((number, _REFERENCE.sub(lookup, content)))
    return substituted, variables
