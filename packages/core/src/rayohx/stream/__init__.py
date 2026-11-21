"""Choosing which stream to download: a variant and its audio and subtitle tracks.

``select_stream`` picks everything for a ``SelectionConfig`` and returns a ``StreamSelection``;
``select_variant`` picks only the video variant, and ``quality_height`` gives the "p" number
the choice is judged by. Each name lives in its own module (``selection``, ``variants`` and
``quality``) and is also available here. Modules starting with an underscore are internal. Names
and modules load the first time they are used, so importing this package loads none of them.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx.stream.quality import quality_height
    from rayohx.stream.selection import StreamSelection, select_stream
    from rayohx.stream.variants import select_variant

_SUBMODULES = frozenset({"quality", "selection", "variants"})
_EXPORTS = {
    "StreamSelection": "rayohx.stream.selection",
    "quality_height": "rayohx.stream.quality",
    "select_stream": "rayohx.stream.selection",
    "select_variant": "rayohx.stream.variants",
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
    "StreamSelection",
    "quality_height",
    "select_stream",
    "select_variant",
]
