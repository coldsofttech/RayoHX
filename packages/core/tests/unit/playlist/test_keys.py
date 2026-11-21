import pytest

from rayohx import ContainerFormat, EncryptionMethod, SegmentRange
from rayohx.errors import InvalidPlaylistError, UnsupportedPlaylistError
from rayohx.playlist._keys import read_key, read_map
from rayohx.playlist.parser import parse_playlist
from tests.helpers.hls import BASE, DIR, media


def test_fmp4_with_initialization_map_and_media_sequence() -> None:
    playlist = media("media_fmp4.m3u8")
    assert playlist.container is ContainerFormat.FMP4
    assert playlist.media_sequence == 100
    assert [segment.sequence_number for segment in playlist.segments] == [100, 101]
    for segment in playlist.segments:
        assert segment.init_map is not None
        assert segment.init_map.uri == f"{DIR}init.mp4"
        assert segment.init_map.byte_range is None


def test_aes_128_keys_apply_until_replaced() -> None:
    segments = media("media_encrypted.m3u8").segments
    first, second, third, clear = (segments[0], segments[1], segments[2], segments[3])
    assert first.encryption is not None
    assert first.encryption.method is EncryptionMethod.AES_128
    assert first.encryption.uri == f"{DIR}keys/one.key"
    assert first.encryption.iv == bytes(range(16))
    assert second.encryption == first.encryption
    assert third.encryption is not None
    assert third.encryption.uri == "https://keys.example.com/two.key?token=hidden"
    assert third.encryption.iv is None
    assert clear.encryption is None
    assert first.encryption.is_supported


def test_sample_aes_is_read_but_flagged_unsupported() -> None:
    encryption = media("media_sample_aes.m3u8").segments[0].encryption
    assert encryption is not None
    assert encryption.method is EncryptionMethod.SAMPLE_AES
    assert encryption.uri == "skd://key"
    assert encryption.key_format == "com.apple.streamingkeydelivery"
    assert encryption.key_format_versions == "1"
    assert not encryption.is_supported


def test_unknown_encryption_method_is_unsupported() -> None:
    text = '#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXT-X-KEY:METHOD=ROT13,URI="k"\n#EXTINF:4,\na.ts\n'
    with pytest.raises(UnsupportedPlaylistError, match="ROT13"):
        parse_playlist(text, BASE)


def test_a_key_tag_gives_the_method_address_and_vector() -> None:
    key = read_key(
        '#EXT-X-KEY:METHOD=AES-128,URI="keys/one.key",IV=0x00112233445566778899aabbccddeeff',
        3,
        BASE,
    )
    assert key is not None
    assert key.method is EncryptionMethod.AES_128
    assert key.uri == f"{DIR}keys/one.key"
    assert key.iv == bytes.fromhex("00112233445566778899aabbccddeeff")
    assert key.key_format == "identity"
    assert key.key_format_versions is None


def test_a_key_format_and_its_versions_are_kept() -> None:
    key = read_key(
        '#EXT-X-KEY:METHOD=SAMPLE-AES,URI="skd://key",KEYFORMAT="com.apple.fps",KEYFORMATVERSIONS="1"',
        3,
        BASE,
    )
    assert key is not None
    assert (key.key_format, key.key_format_versions) == ("com.apple.fps", "1")


def test_a_key_address_may_use_another_scheme() -> None:
    key = read_key('#EXT-X-KEY:METHOD=SAMPLE-AES,URI="skd://key"', 3, BASE)
    assert key is not None
    assert key.uri == "skd://key"


def test_method_none_switches_encryption_off() -> None:
    assert read_key("#EXT-X-KEY:METHOD=NONE", 3, BASE) is None


def test_a_key_without_a_method_is_invalid() -> None:
    with pytest.raises(InvalidPlaylistError, match="needs a METHOD") as info:
        read_key('#EXT-X-KEY:URI="k"', 5, BASE)
    assert info.value.line == 5


def test_an_unknown_method_is_unsupported() -> None:
    with pytest.raises(UnsupportedPlaylistError, match="ROT13"):
        read_key('#EXT-X-KEY:METHOD=ROT13,URI="k"', 5, BASE)


def test_an_encrypted_key_needs_an_address() -> None:
    with pytest.raises(InvalidPlaylistError, match="needs a URI") as info:
        read_key("#EXT-X-KEY:METHOD=AES-128", 5, BASE)
    assert info.value.line == 5


def test_a_bad_vector_is_reported_on_the_line_of_the_tag() -> None:
    with pytest.raises(InvalidPlaylistError, match="initialization vector") as info:
        read_key('#EXT-X-KEY:METHOD=AES-128,URI="k",IV=0xZZ', 9, BASE)
    assert info.value.line == 9


def test_an_init_map_gives_its_address() -> None:
    init = read_map('#EXT-X-MAP:URI="init.mp4"', 2, BASE)
    assert init.uri == f"{DIR}init.mp4"
    assert init.byte_range is None


def test_an_init_map_may_name_a_byte_range() -> None:
    init = read_map('#EXT-X-MAP:URI="init.mp4",BYTERANGE="720@100"', 2, BASE)
    assert init.byte_range == SegmentRange(720, 100)


def test_an_init_map_range_without_an_offset_starts_at_zero() -> None:
    init = read_map('#EXT-X-MAP:URI="init.mp4",BYTERANGE="720"', 2, BASE)
    assert init.byte_range == SegmentRange(720, 0)


def test_an_init_map_without_an_address_is_invalid() -> None:
    with pytest.raises(InvalidPlaylistError, match="needs a URI") as info:
        read_map('#EXT-X-MAP:BYTERANGE="1@0"', 4, BASE)
    assert info.value.line == 4
