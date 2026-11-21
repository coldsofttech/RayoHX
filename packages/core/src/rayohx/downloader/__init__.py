"""Downloading a stream.

* ``download(url, output, ...)`` does the whole job in one call: it takes a web address to a
  finished file and returns a ``DownloadResult``.
* ``Downloader`` is the controller behind it and gives control: create it, subscribe to its
  events, call ``run`` and ``cancel``.

The parts that do the work are internal and live in ``rayohx._download``.

The names below are imported the first time they are used.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx.downloader.batch import BatchItem, batch_outputs, download_many
    from rayohx.downloader.controller import Downloader
    from rayohx.downloader.shortcut import download

_EXPORTS = {
    "BatchItem": "rayohx.downloader.batch",
    "batch_outputs": "rayohx.downloader.batch",
    "download_many": "rayohx.downloader.batch",
    "Downloader": "rayohx.downloader.controller",
    "download": "rayohx.downloader.shortcut",
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
    "BatchItem",
    "Downloader",
    "batch_outputs",
    "download",
    "download_many",
]
