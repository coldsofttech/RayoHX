"""Storage: how much space a download needs, and where finished segments wait for their turn.

Segments finish out of order but must be written in order. A *store* holds the ones that finished
early. The strategies differ in where the store lives:

* ``DIRECT`` and ``STREAMING``: memory, limited to a few segments past the one being written.
* ``BUFFERED``: memory, limited by bytes (``buffer_bytes``).
* ``TEMPORARY``: files in the working folder, so every finished segment survives a crash.
* ``HYBRID``: memory first, then files once the memory limit is reached.

In every case a segment is removed from the store as soon as it is written, so working storage
stays small instead of growing to the size of the stream.

The names below are imported the first time they are used.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx.download._storage._common import DEFAULT_SPILL_BYTES, translate_os_error
    from rayohx.download._storage._metrics import StorageTracker
    from rayohx.download._storage._space import (
        ESTIMATE_MARGIN,
        SizeEstimator,
        SpaceNeed,
        check_disk_space,
        free_bytes,
        nearest_existing,
        same_volume,
        space_needed,
    )
    from rayohx.download._storage._stores import (
        DiskStore,
        MemoryStore,
        SegmentStore,
        SpillStore,
        make_store,
    )
    from rayohx.download._storage._strategy import (
        WINDOW_FACTOR,
        choose_strategy,
        validate_strategy,
    )

_EXPORTS = {
    "DEFAULT_SPILL_BYTES": "rayohx.download._storage._common",
    "DiskStore": "rayohx.download._storage._stores",
    "ESTIMATE_MARGIN": "rayohx.download._storage._space",
    "MemoryStore": "rayohx.download._storage._stores",
    "SegmentStore": "rayohx.download._storage._stores",
    "SizeEstimator": "rayohx.download._storage._space",
    "SpaceNeed": "rayohx.download._storage._space",
    "SpillStore": "rayohx.download._storage._stores",
    "StorageTracker": "rayohx.download._storage._metrics",
    "WINDOW_FACTOR": "rayohx.download._storage._strategy",
    "check_disk_space": "rayohx.download._storage._space",
    "choose_strategy": "rayohx.download._storage._strategy",
    "free_bytes": "rayohx.download._storage._space",
    "make_store": "rayohx.download._storage._stores",
    "nearest_existing": "rayohx.download._storage._space",
    "same_volume": "rayohx.download._storage._space",
    "space_needed": "rayohx.download._storage._space",
    "translate_os_error": "rayohx.download._storage._common",
    "validate_strategy": "rayohx.download._storage._strategy",
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
    "DEFAULT_SPILL_BYTES",
    "ESTIMATE_MARGIN",
    "WINDOW_FACTOR",
    "DiskStore",
    "MemoryStore",
    "SegmentStore",
    "SizeEstimator",
    "SpaceNeed",
    "SpillStore",
    "StorageTracker",
    "check_disk_space",
    "choose_strategy",
    "free_bytes",
    "make_store",
    "nearest_existing",
    "same_volume",
    "space_needed",
    "translate_os_error",
    "validate_strategy",
]
