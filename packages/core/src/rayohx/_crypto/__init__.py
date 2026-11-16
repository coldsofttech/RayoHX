"""HLS AES-128 segment decryption and key retrieval, internal to the engine.

Only ``METHOD=AES-128`` with the standard key format is handled. SAMPLE-AES and DRM key formats
are refused up front by ``require_supported_encryption``. Keys are fetched through the HTTP layer,
so the configured headers and cookies apply (to the key server's host only if it is trusted for
credentials).

The names below are imported the first time they are used, so loading this package does not load
``cryptography`` or the HTTP layer until they are needed.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx._crypto._cipher import decrypt_aes128, decrypt_segment, derive_iv
    from rayohx._crypto._keys import KeyProvider
    from rayohx._crypto._support import require_supported_encryption

_EXPORTS = {
    "KeyProvider": "rayohx._crypto._keys",
    "decrypt_aes128": "rayohx._crypto._cipher",
    "decrypt_segment": "rayohx._crypto._cipher",
    "derive_iv": "rayohx._crypto._cipher",
    "require_supported_encryption": "rayohx._crypto._support",
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
    "KeyProvider",
    "decrypt_aes128",
    "decrypt_segment",
    "derive_iv",
    "require_supported_encryption",
]
