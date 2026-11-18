"""The RayoHX platform: the persistent services built around the download engine.

The engine decides *how* a stream is downloaded; the platform decides *what* should happen:
which downloads run, when, with which profile, and what is remembered between runs. Queue,
scheduler, profiles, automation, notifications, diagnostics and plugins all live here.

Rules (checked by ``tests/unit/test_architecture.py``):

* The engine never imports this package.
* This package imports only the engine's public modules, never ``rayohx._*``.
* Front ends (command line, API, window, browser host) call this package and the public engine;
  none of them holds download logic.

This package is **unstable** until the platform's first release: names and storage formats may
change between versions of ``rayohx``. The engine's public API is not affected.

The names below are imported the first time they are used.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx.platform.errors import PersistenceError, SchemaTooNewError
    from rayohx.platform.events import (
        EventBus,
        EventCategory,
        EventStore,
        PlatformEvent,
        Severity,
    )
    from rayohx.platform.facade import Rayo
    from rayohx.platform.paths import PlatformPaths, resolve_paths
    from rayohx.platform.persistence import Database, SettingsStore

_EXPORTS = {
    "Database": "rayohx.platform.persistence",
    "EventBus": "rayohx.platform.events",
    "EventCategory": "rayohx.platform.events",
    "EventStore": "rayohx.platform.events",
    "PersistenceError": "rayohx.platform.errors",
    "PlatformEvent": "rayohx.platform.events",
    "PlatformPaths": "rayohx.platform.paths",
    "Rayo": "rayohx.platform.facade",
    "SchemaTooNewError": "rayohx.platform.errors",
    "SettingsStore": "rayohx.platform.persistence",
    "Severity": "rayohx.platform.events",
    "resolve_paths": "rayohx.platform.paths",
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
    "Database",
    "EventBus",
    "EventCategory",
    "EventStore",
    "PersistenceError",
    "PlatformEvent",
    "PlatformPaths",
    "Rayo",
    "SchemaTooNewError",
    "SettingsStore",
    "Severity",
    "resolve_paths",
]
