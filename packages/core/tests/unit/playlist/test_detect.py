import pytest

from rayohx.playlist.detect import HEADER, is_hls_playlist


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("#EXTM3U\n#EXTINF:1,\na.ts", True),
        ("﻿#EXTM3U\n", True),
        ("\n  #EXTM3U\n", True),
        ("<html></html>", False),
        ("", False),
        ("#EXTINF:1,\n", False),
    ],
)
def test_is_hls_playlist_looks_at_content(text: str, expected: bool) -> None:
    assert is_hls_playlist(text) is expected


def test_the_header_is_extm3u() -> None:
    assert HEADER == "#EXTM3U"


def test_the_header_has_to_come_first() -> None:
    assert is_hls_playlist("#EXT-X-VERSION:3\n#EXTM3U\n") is False
    assert is_hls_playlist("# a comment\n#EXTM3U\n") is False
