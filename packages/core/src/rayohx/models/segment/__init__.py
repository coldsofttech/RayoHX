"""Segments: one media segment, its byte range, encryption, init map and downloaded data.

The names below are imported the first time they are used.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx.models.segment.data import SegmentData
    from rayohx.models.segment.encryption import EncryptionInfo
    from rayohx.models.segment.init_map import InitMap
    from rayohx.models.segment.range import SegmentRange
    from rayohx.models.segment.segment import Segment

_EXPORTS = {
    "EncryptionInfo": "rayohx.models.segment.encryption",
    "InitMap": "rayohx.models.segment.init_map",
    "Segment": "rayohx.models.segment.segment",
    "SegmentData": "rayohx.models.segment.data",
    "SegmentRange": "rayohx.models.segment.range",
}


def __getattr__(name: str) -> Any:
    """Import a name the first time it is used."""
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_EXPORTS})


__all__ = [
    "EncryptionInfo",
    "InitMap",
    "Segment",
    "SegmentData",
    "SegmentRange",
]
