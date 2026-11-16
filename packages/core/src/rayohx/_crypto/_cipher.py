"""AES-128-CBC decryption of segments and the choice of the IV."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rayohx.errors import DecryptionError

if TYPE_CHECKING:
    from rayohx.models import Segment

KEY_SIZE = 16
BLOCK_SIZE = 16


def derive_iv(segment: Segment) -> bytes:
    """The IV for ``segment``: the playlist's, or the segment's sequence number (RFC 8216)."""
    encryption = segment.encryption
    if encryption is not None and encryption.iv is not None:
        return encryption.iv
    return segment.sequence_number.to_bytes(16, "big")


def decrypt_aes128(data: bytes, key: bytes, iv: bytes) -> bytes:
    """Decrypt AES-128-CBC data with PKCS#7 padding.

    Raises:
        DecryptionError: If the data is not whole blocks or the padding is wrong.
    """
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    if len(key) != KEY_SIZE or len(iv) != BLOCK_SIZE:
        raise DecryptionError("The key and the initialization vector must be 16 bytes each.")
    if not data or len(data) % BLOCK_SIZE:
        raise DecryptionError(
            "The encrypted data is not a whole number of blocks.",
            hint="The segment may be cut short or not encrypted as the playlist says.",
        )
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(data) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    try:
        return unpadder.update(padded) + unpadder.finalize()
    except ValueError:
        raise DecryptionError(
            "The segment could not be decrypted.",
            hint="The key is probably wrong or has expired. Check the key server's access.",
        ) from None


def decrypt_segment(data: bytes, segment: Segment, key: bytes) -> bytes:
    """Decrypt one segment's media bytes with ``key`` and the segment's IV."""
    return decrypt_aes128(data, key, derive_iv(segment))
