from datetime import UTC, datetime

import pytest

from rayohx import Resolution, SegmentRange
from rayohx.errors import InvalidPlaylistError, UnsupportedPlaylistError
from rayohx.playlist._values import (
    byte_range,
    date_time,
    decimal,
    integer,
    resolution,
    resolve,
    split_list,
    whole_tag_number,
)
from tests.helpers.hls import BASE, DIR

# --- addresses ---------------------------------------------------------------------------------


def test_a_relative_address_is_resolved_against_the_playlist() -> None:
    assert resolve(BASE, "seg.ts", 1) == f"{DIR}seg.ts"
    assert resolve(BASE, "../shared/a.ts", 1) == "https://media.example.com/vod/shared/a.ts"
    assert resolve(BASE, "/root/b.ts", 1) == "https://media.example.com/root/b.ts"


def test_an_absolute_address_is_kept() -> None:
    assert (
        resolve(BASE, "https://cdn.example.net/a.ts?x=1", 1) == "https://cdn.example.net/a.ts?x=1"
    )


@pytest.mark.parametrize("reference", ["a\x01b.ts", "a\x7fb.ts", "a\nb.ts"])
def test_an_address_with_control_characters_is_refused(reference: str) -> None:
    with pytest.raises(InvalidPlaylistError, match="control characters") as info:
        resolve(BASE, reference, 7)
    assert info.value.line == 7


def test_only_web_addresses_are_accepted_by_default() -> None:
    with pytest.raises(UnsupportedPlaylistError, match="http and https"):
        resolve(BASE, "ftp://example.com/a.ts", 3)


def test_a_key_address_may_use_another_scheme() -> None:
    assert resolve(BASE, "skd://key", 3, web_only=False) == "skd://key"


# --- numbers -----------------------------------------------------------------------------------


def test_a_whole_number_attribute_is_read() -> None:
    assert integer({"BANDWIDTH": "800000"}, "BANDWIDTH", 1) == 800000


def test_a_missing_number_is_none_unless_it_is_required() -> None:
    assert integer({}, "BANDWIDTH", 1) is None
    with pytest.raises(InvalidPlaylistError, match="Missing required attribute BANDWIDTH") as info:
        integer({}, "BANDWIDTH", 4, required=True)
    assert info.value.line == 4


@pytest.mark.parametrize("value", ["abc", "-1", "1.5", "", "1e3"])
def test_something_that_is_not_a_whole_number_is_refused(value: str) -> None:
    with pytest.raises(InvalidPlaylistError, match="must be a whole number"):
        integer({"BANDWIDTH": value}, "BANDWIDTH", 1)


def test_a_decimal_attribute_is_read() -> None:
    assert decimal({"FRAME-RATE": "29.97"}, "FRAME-RATE", 1) == 29.97
    assert decimal({"FRAME-RATE": "25"}, "FRAME-RATE", 1) == 25.0
    assert decimal({"FRAME-RATE": "0"}, "FRAME-RATE", 1) == 0.0
    assert decimal({}, "FRAME-RATE", 1) is None


def test_something_that_is_not_a_number_is_refused() -> None:
    with pytest.raises(InvalidPlaylistError, match="must be a number"):
        decimal({"FRAME-RATE": "fast"}, "FRAME-RATE", 1)


@pytest.mark.parametrize("value", ["-1", "inf", "nan"])
def test_a_negative_or_infinite_number_is_refused(value: str) -> None:
    with pytest.raises(InvalidPlaylistError, match="finite positive number"):
        decimal({"FRAME-RATE": value}, "FRAME-RATE", 1)


def test_a_tag_with_a_whole_number_is_read() -> None:
    assert whole_tag_number("#EXT-X-VERSION:6", 1) == 6
    assert whole_tag_number("#EXT-X-VERSION: 7 ", 1) == 7


@pytest.mark.parametrize("content", ["#EXT-X-VERSION:abc", "#EXT-X-VERSION:", "#EXT-X-VERSION:-2"])
def test_a_tag_without_a_whole_number_is_refused(content: str) -> None:
    with pytest.raises(InvalidPlaylistError, match="EXT-X-VERSION needs a whole number") as info:
        whole_tag_number(content, 6)
    assert info.value.line == 6


# --- lists, sizes and ranges -------------------------------------------------------------------


def test_a_comma_separated_list_is_split_and_trimmed() -> None:
    assert split_list("avc1.4d401e, mp4a.40.2 ,,x") == ("avc1.4d401e", "mp4a.40.2", "x")
    assert split_list(None) == ()
    assert split_list("") == ()


def test_a_resolution_attribute_is_read() -> None:
    assert resolution({"RESOLUTION": "1280x720"}, 1) == Resolution(1280, 720)
    assert resolution({}, 1) is None


def test_a_bad_resolution_is_reported_on_the_line_of_the_tag() -> None:
    with pytest.raises(InvalidPlaylistError, match="not a valid resolution") as info:
        resolution({"RESOLUTION": "big"}, 5)
    assert info.value.line == 5


def test_a_byte_range_is_read_with_and_without_an_offset() -> None:
    assert byte_range("1000@720", 1) == SegmentRange(1000, 720)
    assert byte_range("500", 1) == SegmentRange(500, None)


def test_a_bad_byte_range_is_reported_on_the_line_of_the_tag() -> None:
    with pytest.raises(InvalidPlaylistError, match="not a valid byte range") as info:
        byte_range("0", 8)
    assert info.value.line == 8


# --- dates -------------------------------------------------------------------------------------


def test_a_date_with_a_time_zone_is_read() -> None:
    assert date_time("2026-01-02T03:04:05.250Z", 1) == datetime(
        2026, 1, 2, 3, 4, 5, 250000, tzinfo=UTC
    )


def test_something_that_is_not_a_date_is_reported_on_the_line_of_the_tag() -> None:
    with pytest.raises(InvalidPlaylistError, match="not a valid date") as info:
        date_time("yesterday", 11)
    assert info.value.line == 11
