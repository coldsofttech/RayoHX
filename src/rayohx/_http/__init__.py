"""The HTTP layer, internal to the engine. Use ``rayohx.inspect`` or the download API instead.

The names below are imported the first time they are used, so loading this package does not load
``httpx`` until a request is made.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx._http._client import HttpClient
    from rayohx._http._response import HttpResponse

_EXPORTS = {
    "HttpClient": "rayohx._http._client",
    "HttpResponse": "rayohx._http._response",
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


__all__ = ["HttpClient", "HttpResponse"]
