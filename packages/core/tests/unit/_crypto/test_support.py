import pytest

from rayohx import EncryptionInfo, EncryptionMethod
from rayohx._crypto import (
    require_supported_encryption,
)
from rayohx.errors import (
    UnsupportedPlaylistError,
)
from tests.helpers.crypto import segment


def test_only_plain_aes_128_is_supported() -> None:
    require_supported_encryption([segment(), segment(encryption=None)])
    sample = EncryptionInfo(EncryptionMethod.SAMPLE_AES, "skd://k", key_format="com.apple.fps")
    with pytest.raises(UnsupportedPlaylistError, match="SAMPLE-AES") as info:
        require_supported_encryption([segment(), segment(encryption=sample)])
    assert "DRM" in (info.value.hint or "")
    drm = EncryptionInfo(EncryptionMethod.AES_128, "skd://k", key_format="com.example.drm")
    with pytest.raises(UnsupportedPlaylistError):
        require_supported_encryption([segment(encryption=drm)])
