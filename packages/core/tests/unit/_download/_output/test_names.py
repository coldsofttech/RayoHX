import pytest

from rayohx import ContainerFormat
from rayohx._download._output import (
    MAX_NAME_LENGTH,
    name_from_url,
    sanitize_filename,
    segment_file_name,
)

TS = ContainerFormat.MPEG_TS


MP4 = ContainerFormat.FMP4


def test_segment_file_names_sort_in_order() -> None:
    assert segment_file_name(0, TS) == "segment-00001.ts"
    assert segment_file_name(11, MP4) == "segment-00012.m4s"
    assert segment_file_name(3, MP4, init=True) == "init-00003.mp4"
    assert segment_file_name(0, ContainerFormat.UNKNOWN).endswith(".bin")
    names = [segment_file_name(i, TS) for i in range(1500)]
    assert names == sorted(names)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("My Show", "My_Show"),
        ("../../etc/passwd", "etc_passwd"),
        ("..\\..\\windows\\system32", "windows_system32"),
        ("/absolute/path", "absolute_path"),
        ("a" * 300, "a" * MAX_NAME_LENGTH),
        ("  ..hidden  ", "hidden"),
        ("café ☕ 日本語", "caf"),
        ("name:with*bad?chars<>|", "name_with_bad_chars"),
        ("", "video"),
        ("...", "video"),
        ("日本語", "video"),
        ("CON", "_CON"),
        ("aux.txt", "_aux.txt"),
        ("COM1", "_COM1"),
        ("lpt9", "_lpt9"),
        ("console", "console"),
        ("a\x00b\nc", "a_b_c"),
    ],
)
def test_sanitised_names_are_safe(text: str, expected: str) -> None:
    assert sanitize_filename(text) == expected


def test_sanitised_names_never_escape_their_folder() -> None:
    for hostile in ["../x", "..", ".", "a/../../b", "~root", "$(rm -rf)", "\\\\server\\share"]:
        name = sanitize_filename(hostile)
        assert "/" not in name
        assert "\\" not in name
        assert not name.startswith(".")
        assert name


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://h/shows/my-show/index.m3u8", "my-show"),
        ("https://h/movie.m3u8?token=abc", "movie"),
        ("https://h/a/b/master.m3u8", "b"),
        ("https://h/Some%20Title/playlist.m3u8", "Some_Title"),
        ("https://h/", "video"),
        ("https://h/index.m3u8", "video"),
        ("https://h/%2e%2e/%2e%2e/evil.m3u8", "evil"),
    ],
)
def test_names_from_addresses(url: str, expected: str) -> None:
    assert name_from_url(url) == expected
