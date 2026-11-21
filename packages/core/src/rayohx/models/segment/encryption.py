"""An ``EXT-X-KEY`` entry."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rayohx.enums import EncryptionMethod

_IV = re.compile(r"^0[xX]([0-9A-Fa-f]{1,32})$")


@dataclass(frozen=True, slots=True)
class EncryptionInfo:
    """An ``EXT-X-KEY`` entry. The key itself is fetched later, through the HTTP layer."""

    method: EncryptionMethod
    uri: str | None = None
    iv: bytes | None = None
    key_format: str = "identity"
    key_format_versions: str | None = None

    def __post_init__(self) -> None:
        from rayohx.enums import EncryptionMethod

        if self.method is not EncryptionMethod.NONE and not self.uri:
            raise ValueError("an encrypted segment needs a key address")
        if self.iv is not None and len(self.iv) != 16:
            raise ValueError("the initialization vector must be 16 bytes")

    @staticmethod
    def parse_iv(text: str) -> bytes:
        """Read an ``IV`` attribute such as ``0x00112233445566778899aabbccddeeff``.

        Raises:
            InvalidPlaylistError: If ``text`` is not a hexadecimal number of up to 128 bits.
        """
        match = _IV.match(text.strip())
        if not match:
            from rayohx.errors import InvalidPlaylistError

            raise InvalidPlaylistError(f"{text!r} is not a valid initialization vector.")
        return bytes.fromhex(match.group(1).rjust(32, "0"))

    @property
    def is_supported(self) -> bool:
        """Whether the engine can decrypt this entry (plain AES-128, no DRM key format)."""
        from rayohx.enums import EncryptionMethod

        if self.method is EncryptionMethod.NONE:
            return True
        return self.method is EncryptionMethod.AES_128 and self.key_format == "identity"
