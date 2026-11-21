"""Models that describe a download: the request, its progress and its result.

The names below are imported the first time they are used.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx.models.download.output import OutputInfo
    from rayohx.models.download.progress import DownloadProgress
    from rayohx.models.download.request import DownloadRequest
    from rayohx.models.download.result import DownloadResult
    from rayohx.models.download.storage import StorageMetrics

_EXPORTS = {
    "DownloadProgress": "rayohx.models.download.progress",
    "DownloadRequest": "rayohx.models.download.request",
    "DownloadResult": "rayohx.models.download.result",
    "OutputInfo": "rayohx.models.download.output",
    "StorageMetrics": "rayohx.models.download.storage",
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
    "DownloadProgress",
    "DownloadRequest",
    "DownloadResult",
    "OutputInfo",
    "StorageMetrics",
]
