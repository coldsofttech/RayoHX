import pytest
from rayohx_pytest.media import encrypt

from rayohx import EncryptionInfo, EncryptionMethod
from rayohx._crypto import (
    decrypt_aes128,
    decrypt_segment,
    derive_iv,
)
from rayohx.errors import (
    DecryptionError,
)
from tests.helpers.crypto import DATA, segment
from tests.helpers.media import BASE, IV, KEY


def test_decrypt_round_trip() -> None:
    assert decrypt_aes128(encrypt(DATA, KEY, IV), KEY, IV) == DATA


def test_a_wrong_key_is_reported_clearly() -> None:
    with pytest.raises(DecryptionError, match="could not be decrypted") as info:
        decrypt_aes128(encrypt(DATA, KEY, IV), bytes(16), IV)
    assert info.value.hint


@pytest.mark.parametrize("data", [b"", b"x" * 15, b"x" * 17])
def test_data_that_is_not_whole_blocks_is_rejected(data: bytes) -> None:
    with pytest.raises(DecryptionError, match="blocks"):
        decrypt_aes128(data, KEY, IV)


def test_key_and_iv_sizes_are_checked() -> None:
    with pytest.raises(DecryptionError, match="16 bytes"):
        decrypt_aes128(b"x" * 16, KEY[:8], IV)
    with pytest.raises(DecryptionError, match="16 bytes"):
        decrypt_aes128(b"x" * 16, KEY, IV[:8])


def test_the_iv_comes_from_the_playlist_or_the_sequence_number() -> None:
    assert derive_iv(segment(sequence=9)) == IV
    implicit = EncryptionInfo(EncryptionMethod.AES_128, BASE + "key.bin")
    assert derive_iv(segment(sequence=9, encryption=implicit)) == (9).to_bytes(16, "big")
    assert derive_iv(segment(sequence=0, encryption=None)) == bytes(16)
    big = 2**100 + 7
    assert derive_iv(segment(sequence=big, encryption=implicit)) == big.to_bytes(16, "big")


def test_decrypt_segment_uses_the_segments_iv() -> None:
    implicit = EncryptionInfo(EncryptionMethod.AES_128, BASE + "key.bin")
    iv = (5).to_bytes(16, "big")
    assert decrypt_segment(encrypt(DATA, KEY, iv), segment(5, implicit), KEY) == DATA
