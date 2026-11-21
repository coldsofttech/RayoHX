import pytest

from rayohx.errors import InvalidPlaylistError
from rayohx.playlist.attributes import parse_attribute_list


def test_attribute_list_handles_quotes_spaces_and_order() -> None:
    parsed = parse_attribute_list('B=2, A="x, y=z" ,C=3')
    assert parsed == {"B": "2", "A": "x, y=z", "C": "3"}
    assert parse_attribute_list("") == {}
    assert parse_attribute_list('URI=""') == {"URI": ""}


@pytest.mark.parametrize("text", ["NOVALUE", 'A="open', "a=1", 'A="x"B=2', "=1"])
def test_attribute_list_rejects_malformed_text(text: str) -> None:
    with pytest.raises(InvalidPlaylistError):
        parse_attribute_list(text, line=3)


def test_attributes_can_be_separated_by_tabs_and_spaces() -> None:
    assert parse_attribute_list("A=1,\tB=2 , C=3") == {"A": "1", "B": "2", "C": "3"}


def test_a_quoted_value_keeps_its_commas_and_equals_signs() -> None:
    assert parse_attribute_list('CODECS="avc1.4d401e,mp4a.40.2",NAME="a=b"') == {
        "CODECS": "avc1.4d401e,mp4a.40.2",
        "NAME": "a=b",
    }


def test_a_repeated_attribute_keeps_the_last_value() -> None:
    assert parse_attribute_list("A=1,A=2") == {"A": "2"}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("NOVALUE", "without a value"),
        ("a=1", "Invalid attribute name"),
        ('A="open', "Unterminated"),
        ('A="x"B=2', "Expected a comma"),
    ],
)
def test_each_kind_of_malformed_list_is_explained(text: str, message: str) -> None:
    with pytest.raises(InvalidPlaylistError, match=message):
        parse_attribute_list(text)


def test_an_error_carries_the_line_it_was_found_on() -> None:
    with pytest.raises(InvalidPlaylistError) as info:
        parse_attribute_list("NOVALUE", line=7)
    assert info.value.line == 7
    with pytest.raises(InvalidPlaylistError) as without:
        parse_attribute_list("NOVALUE")
    assert without.value.line is None
