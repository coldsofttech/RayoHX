"""Reading and checking the values inside tags."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from rayohx.models import Resolution, SegmentRange


def resolve(base: str, reference: str, line: int, *, web_only: bool = True) -> str:
    """Resolve ``reference`` against ``base``.

    Media and playlist addresses must be web addresses. A key address may use another scheme
    (such as ``skd://``); it is kept so the playlist can still be inspected.
    """
    from urllib.parse import urljoin, urlsplit

    if any(ord(char) < 32 or char == "\x7f" for char in reference):
        from rayohx.errors import InvalidPlaylistError

        raise InvalidPlaylistError("An address contains control characters.", line=line)
    absolute = urljoin(base, reference)
    if web_only and urlsplit(absolute).scheme.lower() not in {"http", "https"}:
        from rayohx.errors import UnsupportedPlaylistError

        raise UnsupportedPlaylistError(
            f"Only http and https addresses are supported, found {reference!r} (line {line})."
        )
    return absolute


def integer(
    attributes: dict[str, str], name: str, line: int, *, required: bool = False
) -> int | None:
    value = attributes.get(name)
    if value is None:
        if required:
            from rayohx.errors import InvalidPlaylistError

            raise InvalidPlaylistError(f"Missing required attribute {name}.", line=line)
        return None
    if not value.isdigit():
        from rayohx.errors import InvalidPlaylistError

        raise InvalidPlaylistError(f"{name} must be a whole number, found {value!r}.", line=line)
    return int(value)


def decimal(attributes: dict[str, str], name: str, line: int) -> float | None:
    value = attributes.get(name)
    if value is None:
        return None
    try:
        number = float(value)
    except ValueError:
        from rayohx.errors import InvalidPlaylistError

        raise InvalidPlaylistError(
            f"{name} must be a number, found {value!r}.", line=line
        ) from None
    if number < 0 or number != number or number == float("inf"):
        from rayohx.errors import InvalidPlaylistError

        raise InvalidPlaylistError(f"{name} must be a finite positive number.", line=line)
    return number


def whole_tag_number(content: str, line: int) -> int:
    from rayohx.playlist._lines import tag_value

    value = tag_value(content).strip()
    if not value.isdigit():
        from rayohx.errors import InvalidPlaylistError
        from rayohx.playlist._lines import tag_name

        raise InvalidPlaylistError(f"{tag_name(content)} needs a whole number.", line=line)
    return int(value)


def split_list(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def resolution(attributes: dict[str, str], line: int) -> Resolution | None:
    value = attributes.get("RESOLUTION")
    if value is None:
        return None
    from rayohx.errors import InvalidPlaylistError
    from rayohx.models import Resolution

    try:
        return Resolution.parse(value)
    except InvalidPlaylistError as exc:
        raise InvalidPlaylistError(exc.message, line=line) from None


def byte_range(value: str, line: int) -> SegmentRange:
    from rayohx.errors import InvalidPlaylistError
    from rayohx.models import SegmentRange

    try:
        return SegmentRange.parse(value)
    except InvalidPlaylistError as exc:
        raise InvalidPlaylistError(exc.message, line=line) from None


def date_time(value: str, line: int) -> datetime:
    from datetime import datetime

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        from rayohx.errors import InvalidPlaylistError

        raise InvalidPlaylistError(
            f"#EXT-X-PROGRAM-DATE-TIME is not a valid date: {value!r}.", line=line
        ) from None
