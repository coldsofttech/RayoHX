"""``EXT-X-DEFINE`` variables."""

import pytest

from rayohx import MasterPlaylist, MediaPlaylist
from rayohx.errors import InvalidPlaylistError, UnsupportedPlaylistError
from rayohx.playlist import parse_playlist
from tests.helpers.hls import fixture_text

BASE = "https://cdn.example.com/vod/index.m3u8"

MASTER = fixture_text("master_variables.m3u8")
MEDIA = fixture_text("media_variables.m3u8")


def test_master_variables_are_replaced_and_kept() -> None:
    master = parse_playlist(MASTER, BASE)
    assert isinstance(master, MasterPlaylist)
    assert master.variants[0].uri == "https://media.example.com/hd/video.m3u8"
    assert dict(master.variables) == {"host": "media.example.com", "quality": "hd"}


def test_media_variables_and_query_parameters() -> None:
    media = parse_playlist(MEDIA, BASE + "?token=abc%20d")
    assert isinstance(media, MediaPlaylist)
    assert media.segments[0].uri == "https://cdn.example.com/s/1.ts?t=abc%20d"


def test_import_takes_the_master_value() -> None:
    text = MEDIA.replace('QUERYPARAM="token"', 'IMPORT="host"').replace("{$token}", "{$host}")
    media = parse_playlist(text, BASE, variables={"host": "h"})
    assert isinstance(media, MediaPlaylist)
    assert media.segments[0].uri.endswith("?t=h")


def test_import_without_a_master_is_unsupported() -> None:
    text = MEDIA.replace('QUERYPARAM="token"', 'IMPORT="host"').replace("{$token}", "{$host}")
    with pytest.raises(UnsupportedPlaylistError, match="master"):
        parse_playlist(text, BASE)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (MEDIA.replace("{$seg}", "{$nope}"), "not defined"),
        (MEDIA.replace('QUERYPARAM="token"', 'NAME="seg",VALUE="x"'), "twice"),
        (MEDIA.replace('QUERYPARAM="token"', 'NAME="bad name",VALUE="x"'), "valid variable name"),
        (MEDIA.replace('QUERYPARAM="token"', 'FOO="x"'), "needs NAME"),
    ],
)
def test_bad_variables_are_refused(text: str, message: str) -> None:
    with pytest.raises(InvalidPlaylistError, match=message):
        parse_playlist(text, BASE + "?token=1")


def test_missing_query_parameter_is_refused() -> None:
    with pytest.raises(InvalidPlaylistError, match="token"):
        parse_playlist(MEDIA, BASE)


def test_import_of_an_unknown_variable_is_refused() -> None:
    text = MEDIA.replace('QUERYPARAM="token"', 'IMPORT="zzz"').replace("{$token}", "x")
    with pytest.raises(InvalidPlaylistError, match="zzz"):
        parse_playlist(text, BASE, variables={})


def test_inspect_text_parses_a_playlist_you_have() -> None:
    from rayohx import inspect_text

    media = inspect_text(MEDIA.replace('QUERYPARAM="token"', 'NAME="token",VALUE="t"'), BASE)
    assert isinstance(media, MediaPlaylist)
    with pytest.raises(InvalidPlaylistError, match="EXTM3U"):
        inspect_text("<html>", BASE)
