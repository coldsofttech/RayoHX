"""Typed, validated settings.

Every object is immutable and checks itself on creation, so a bad value fails at the edge with a
``ConfigurationError`` instead of deep inside a download. Secrets are kept out of ``repr`` and out
of ``as_dict``. Each area lives in its own module (``proxy``, ``network``, ``storage``, ``output``,
``selection`` and ``download``) and is also available here, for example
``rayohx.config.NetworkConfig``.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rayohx.config.download import DownloadConfig
    from rayohx.config.network import NetworkConfig
    from rayohx.config.output import OutputConfig
    from rayohx.config.proxy import ProxyConfig
    from rayohx.config.selection import SelectionConfig
    from rayohx.config.storage import StorageConfig
    from rayohx.config.url import validate_url

__all__ = [
    "DownloadConfig",
    "NetworkConfig",
    "OutputConfig",
    "ProxyConfig",
    "SelectionConfig",
    "StorageConfig",
    "validate_url",
]

#: Where each public name lives. A name is imported on first use, so importing this package does
#: not load every settings module.
_EXPORTS = {
    "DownloadConfig": "rayohx.config.download",
    "NetworkConfig": "rayohx.config.network",
    "OutputConfig": "rayohx.config.output",
    "ProxyConfig": "rayohx.config.proxy",
    "SelectionConfig": "rayohx.config.selection",
    "StorageConfig": "rayohx.config.storage",
    "validate_url": "rayohx.config.url",
}


def __getattr__(name: str) -> object:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module), name)
    globals()[name] = value  # found once, then served as a plain attribute
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})
