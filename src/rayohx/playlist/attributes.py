"""Attribute lists such as ``KEY=value,KEY="quoted, value"``."""

import re

from rayohx.errors import InvalidPlaylistError

_ATTRIBUTE_NAME = re.compile(r"^[A-Z0-9-]+$")


def parse_attribute_list(text: str, *, line: int | None = None) -> dict[str, str]:
    """Split ``KEY=value,KEY="quoted, value"`` into a dictionary, in any order.

    Quotes are removed from quoted values.

    Raises:
        InvalidPlaylistError: If the list is malformed.
    """
    attributes: dict[str, str] = {}
    length = len(text)
    position = 0
    while position < length:
        while position < length and text[position] in " \t":
            position += 1
        if position >= length:
            break
        equals = text.find("=", position)
        if equals == -1:
            raise InvalidPlaylistError(
                f"Attribute without a value: {text[position:]!r}.", line=line
            )
        name = text[position:equals].strip()
        if not _ATTRIBUTE_NAME.match(name):
            raise InvalidPlaylistError(f"Invalid attribute name {name!r}.", line=line)
        position = equals + 1
        if position < length and text[position] == '"':
            end = text.find('"', position + 1)
            if end == -1:
                raise InvalidPlaylistError(f"Unterminated quoted value for {name}.", line=line)
            value = text[position + 1 : end]
            position = end + 1
        else:
            end = text.find(",", position)
            end = length if end == -1 else end
            value = text[position:end].strip()
            position = end
        attributes[name] = value
        while position < length and text[position] in " \t":
            position += 1
        if position < length:
            if text[position] != ",":
                raise InvalidPlaylistError(f"Expected a comma after {name}.", line=line)
            position += 1
    return attributes
