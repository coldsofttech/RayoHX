"""HLS playlists: reading them (RFC 8216) and looking at a stream before downloading it.

``is_hls_playlist`` recognises a playlist, ``parse_playlist`` and ``parse_attribute_list`` read
one, and ``inspect_playlist`` fetches and parses one without downloading media (through any
``PlaylistFetcher``). Each name lives in its own module (``detect``, ``parser``, ``attributes`` and
``inspection``) and is also available here. Modules starting with an underscore are internal.
Names and modules load the first time they are used, so importing this package loads none of them.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx.playlist.attributes import parse_attribute_list
    from rayohx.playlist.detect import is_hls_playlist
    from rayohx.playlist.inspection import PlaylistFetcher, inspect_playlist
    from rayohx.playlist.parser import parse_playlist

_SUBMODULES = frozenset({"attributes", "detect", "inspection", "parser"})
_EXPORTS = {
    "PlaylistFetcher": "rayohx.playlist.inspection",
    "inspect_playlist": "rayohx.playlist.inspection",
    "is_hls_playlist": "rayohx.playlist.detect",
    "parse_attribute_list": "rayohx.playlist.attributes",
    "parse_playlist": "rayohx.playlist.parser",
}


def __getattr__(name: str) -> Any:
    """Import a public name the first time it is used."""
    if name in _SUBMODULES:
        value = import_module(f"{__name__}.{name}")
        globals()[name] = value
        return value
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_EXPORTS, *_SUBMODULES})


__all__ = [
    "PlaylistFetcher",
    "inspect_playlist",
    "is_hls_playlist",
    "parse_attribute_list",
    "parse_playlist",
]
