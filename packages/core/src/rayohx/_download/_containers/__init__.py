"""Recognising and checking segment formats.

RayoHX joins MPEG-TS and fragmented MP4 segments by simple concatenation, which is only valid when
the pieces really are that format. These checks catch the common failures (an error page served as
media, a wrong decryption key, a cut-off file) before they turn into a corrupt output that looks
like a success.

* ``sniff_container`` guesses the format from the first bytes of a segment.
* ``check_segment`` checks one downloaded segment against the promised format.
* ``validate_output`` (with ``validate_ts_file`` and ``validate_fmp4_file``) checks a finished file.

The names below are imported the first time they are used.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx._download._containers._files import (
        validate_fmp4_file,
        validate_output,
        validate_ts_file,
    )
    from rayohx._download._containers._segments import check_segment
    from rayohx._download._containers._sniff import sniff_container

_EXPORTS = {
    "check_segment": "rayohx._download._containers._segments",
    "sniff_container": "rayohx._download._containers._sniff",
    "validate_fmp4_file": "rayohx._download._containers._files",
    "validate_output": "rayohx._download._containers._files",
    "validate_ts_file": "rayohx._download._containers._files",
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
    "check_segment",
    "sniff_container",
    "validate_fmp4_file",
    "validate_output",
    "validate_ts_file",
]
