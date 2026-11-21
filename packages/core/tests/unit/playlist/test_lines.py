from rayohx import ContainerFormat, MediaPlaylist
from rayohx.playlist._lines import is_comment, numbered_lines, tag_name, tag_value
from rayohx.playlist.parser import parse_playlist
from tests.helpers.hls import BASE


def test_line_endings_bom_and_empty_playlists() -> None:
    text = "﻿#EXTM3U\r\n#EXT-X-TARGETDURATION:4\r#EXTINF:4,\r\na.ts\r\n#EXT-X-ENDLIST\r\n"
    playlist = parse_playlist(text, BASE)
    assert isinstance(playlist, MediaPlaylist)
    assert playlist.segment_count == 1
    empty = parse_playlist("#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXT-X-ENDLIST\n", BASE)
    assert isinstance(empty, MediaPlaylist)
    assert empty.segments == ()
    assert empty.container is ContainerFormat.UNKNOWN


def test_unicode_line_separators_do_not_split_lines() -> None:
    separator = chr(0x2028)
    title = f"Title{separator}with separator"
    text = f"#EXTM3U\n#EXT-X-TARGETDURATION:4\n#EXTINF:4,{title}\na.ts\n"
    playlist = parse_playlist(text, BASE)
    assert isinstance(playlist, MediaPlaylist)
    assert playlist.segments[0].title == title


def test_lines_are_numbered_from_one_and_blank_ones_are_skipped() -> None:
    assert numbered_lines("#EXTM3U\n\n   \nseg.ts\n") == [(1, "#EXTM3U"), (4, "seg.ts")]


def test_each_line_is_stripped() -> None:
    assert numbered_lines("  a  \n\tb\t") == [(1, "a"), (2, "b")]


def test_all_three_kinds_of_line_break_split_lines() -> None:
    assert numbered_lines("a\r\nb\nc\rd") == [(1, "a"), (2, "b"), (3, "c"), (4, "d")]


def test_a_leading_byte_order_mark_is_dropped() -> None:
    assert numbered_lines("\ufeff#EXTM3U\nseg.ts") == [(1, "#EXTM3U"), (2, "seg.ts")]


def test_text_without_lines_has_none() -> None:
    assert numbered_lines("") == []
    assert numbered_lines("\n \n\t\n") == []


def test_the_name_of_a_tag_is_what_follows_the_hash_up_to_the_colon() -> None:
    assert tag_name("#EXTINF:4,title") == "EXTINF"
    assert tag_name("#EXT-X-ENDLIST") == "EXT-X-ENDLIST"


def test_the_value_of_a_tag_is_everything_after_the_first_colon() -> None:
    assert tag_value("#EXTINF:4,title") == "4,title"
    assert tag_value('#EXT-X-KEY:URI="a:b"') == 'URI="a:b"'
    assert tag_value("#EXT-X-ENDLIST") == ""


def test_only_a_hash_line_that_is_not_a_tag_is_a_comment() -> None:
    assert is_comment("# a note")
    assert is_comment("#")
    assert not is_comment("#EXTINF:4")
    assert not is_comment("#EXT-X-FUTURE-TAG")
    assert not is_comment("segment.ts")
    assert not is_comment("")
