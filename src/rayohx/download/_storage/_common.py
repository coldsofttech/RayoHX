"""Limits and helpers shared by the storage modules."""

import errno

from rayohx.errors import InsufficientStorageError, OutputError

#: Disk spill limit of HYBRID when ``max_temp_bytes`` is not set.
DEFAULT_SPILL_BYTES = 1024 * 1024 * 1024


def translate_os_error(exc: OSError, what: str) -> Exception:
    """Turn a failed write into a clear error, recognising a full disk."""
    if exc.errno == errno.ENOSPC or getattr(exc, "winerror", None) == 112:
        return InsufficientStorageError(0, 0, location=what)
    return OutputError(f"Could not write {what}: {exc.strerror or exc}")
