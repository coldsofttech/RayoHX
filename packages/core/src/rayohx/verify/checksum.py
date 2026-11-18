"""Checksums of finished files."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from rayohx.config.verify import CHECKSUM_ALGORITHMS

if TYPE_CHECKING:
    from pathlib import Path

    from rayohx.cancellation import CancellationToken

CHUNK = 1024 * 1024


def file_checksum(path: Path, algorithm: str, cancel: CancellationToken | None = None) -> str:
    """The hexadecimal checksum of ``path``, read in pieces so a large file costs little memory.

    Raises:
        ValueError: If ``algorithm`` is not one of ``md5``, ``sha1``, ``sha256``, ``sha512``.
        CancellationError: If ``cancel`` fires while reading.
    """
    if algorithm not in CHECKSUM_ALGORITHMS:
        raise ValueError(f"unsupported checksum algorithm {algorithm!r}")
    digest = hashlib.new(algorithm, usedforsecurity=False)
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
            if cancel is not None:
                cancel.raise_if_cancelled()
    return digest.hexdigest()
