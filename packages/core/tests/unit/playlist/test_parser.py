import pytest

from rayohx.errors import InvalidPlaylistError, UnsupportedPlaylistError
from rayohx.playlist.parser import parse_playlist
from tests.helpers.hls import BASE, fixture_text


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("malformed_no_header.m3u8", "#EXTM3U"),
        ("web_page.html", "#EXTM3U"),
        ("malformed_stream_without_uri.m3u8", "address"),
        ("malformed_stream_at_end.m3u8", "address"),
        ("malformed_extinf_without_uri.m3u8", "no segment address"),
        ("malformed_uri_without_extinf.m3u8", "#EXTINF"),
        ("malformed_no_targetduration.m3u8", "TARGETDURATION"),
        ("malformed_unterminated_quote.m3u8", "Unterminated"),
        ("malformed_missing_bandwidth.m3u8", "BANDWIDTH"),
        ("malformed_mixed.m3u8", "mixes"),
        ("malformed_empty.m3u8", "neither"),
        ("malformed_relative_range.m3u8", "offset"),
        ("malformed_key_without_uri.m3u8", "URI"),
        ("malformed_iv.m3u8", "initialization vector"),
    ],
)
def test_malformed_playlists_are_rejected_clearly(name: str, message: str) -> None:
    with pytest.raises(InvalidPlaylistError, match=message):
        parse_playlist(fixture_text(name), BASE)


def test_errors_report_the_line() -> None:
    with pytest.raises(InvalidPlaylistError) as info:
        parse_playlist(fixture_text("malformed_iv.m3u8"), BASE)
    assert info.value.line == 3
    with pytest.raises(InvalidPlaylistError) as info:
        parse_playlist(fixture_text("malformed_stream_without_uri.m3u8"), BASE)
    assert info.value.line == 2


def test_not_a_playlist_error_has_a_hint() -> None:
    with pytest.raises(InvalidPlaylistError) as info:
        parse_playlist(fixture_text("web_page.html"), BASE)
    assert info.value.hint


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("unsupported_iframes.m3u8", "I-frame"),
        ("unsupported_scheme.m3u8", "http"),
    ],
)
def test_unsupported_features_are_refused(name: str, message: str) -> None:
    with pytest.raises(UnsupportedPlaylistError, match=message):
        parse_playlist(fixture_text(name), BASE)


@pytest.mark.parametrize(
    "body",
    [
        "#EXT-X-PLAYLIST-TYPE:LIVE\n#EXTINF:4,\na.ts",
        "#EXT-X-PROGRAM-DATE-TIME:yesterday\n#EXTINF:4,\na.ts",
        "#EXT-X-MEDIA-SEQUENCE:abc\n#EXTINF:4,\na.ts",
        "#EXT-X-BYTERANGE:0\n#EXTINF:4,\na.ts",
        "#EXTINF:soon,\na.ts",
        '#EXT-X-MAP:BYTERANGE="1@0"\n#EXTINF:4,\na.ts',
        '#EXT-X-KEY:URI="k"\n#EXTINF:4,\na.ts',
        "#EXTINF:4,\na\x01b.ts",
    ],
)
def test_bad_tag_values_are_invalid(body: str) -> None:
    with pytest.raises(InvalidPlaylistError):
        parse_playlist(f"#EXTM3U\n#EXT-X-TARGETDURATION:4\n{body}\n", BASE)
