"""Refusing playlists whose encryption the engine cannot undo."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rayohx.errors import UnsupportedPlaylistError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from rayohx.models import Segment


def require_supported_encryption(segments: Iterable[Segment]) -> None:
    """Refuse playlists whose encryption the engine cannot undo.

    Only ``METHOD=AES-128`` with the standard key format is handled. SAMPLE-AES and DRM key
    formats are refused up front: RayoHX never claims to support DRM.

    Raises:
        UnsupportedPlaylistError: For SAMPLE-AES or any non-standard key format.
    """
    for segment in segments:
        encryption = segment.encryption
        if encryption is not None and not encryption.is_supported:
            raise UnsupportedPlaylistError(
                f"This stream uses {encryption.method.value} with the key format "
                f"{encryption.key_format!r}, which is not supported.",
                hint="Only plain AES-128 encryption is supported. Protected (DRM) streams "
                "cannot be downloaded.",
            )
