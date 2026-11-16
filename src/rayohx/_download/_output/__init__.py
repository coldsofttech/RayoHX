"""Deciding what the output is called and checking that it matches what is inside.

* ``plan_output`` chooses the output path and format for a stream, and refuses a name that would
  mislabel the content.
* ``sanitize_filename``, ``name_from_url`` and ``segment_file_name`` make safe names.

The names below are imported the first time they are used.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx._download._output._names import (
        MAX_NAME_LENGTH,
        name_from_url,
        sanitize_filename,
        segment_file_name,
    )
    from rayohx._download._output._plan import OutputPlan, plan_output

_EXPORTS = {
    "MAX_NAME_LENGTH": "rayohx._download._output._names",
    "OutputPlan": "rayohx._download._output._plan",
    "name_from_url": "rayohx._download._output._names",
    "plan_output": "rayohx._download._output._plan",
    "sanitize_filename": "rayohx._download._output._names",
    "segment_file_name": "rayohx._download._output._names",
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
    "MAX_NAME_LENGTH",
    "OutputPlan",
    "name_from_url",
    "plan_output",
    "sanitize_filename",
    "segment_file_name",
]
