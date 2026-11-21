import pytest

from rayohx.config._common import check_positive, frozen_map
from rayohx.errors import ConfigurationError


def test_a_frozen_map_has_the_same_items_but_cannot_be_changed() -> None:
    frozen = frozen_map({"a": "1", "b": "2"})
    assert dict(frozen) == {"a": "1", "b": "2"}
    with pytest.raises(TypeError):
        frozen["c"] = "3"  # type: ignore[index]


def test_a_frozen_map_is_a_copy_that_later_changes_to_the_source_do_not_reach() -> None:
    source = {"a": "1"}
    frozen = frozen_map(source)
    source["a"] = "changed"
    source["b"] = "2"
    assert dict(frozen) == {"a": "1"}


@pytest.mark.parametrize("value", [1, 0.001, 10**9])
def test_positive_numbers_are_accepted(value: float) -> None:
    check_positive("size", value)


@pytest.mark.parametrize("value", [0, -1, -0.5])
def test_zero_and_negative_numbers_are_refused(value: float) -> None:
    with pytest.raises(ConfigurationError, match="size must be greater than zero"):
        check_positive("size", value)


def test_a_missing_value_is_refused_unless_none_is_allowed() -> None:
    with pytest.raises(ConfigurationError, match="size is required"):
        check_positive("size", None)
    check_positive("size", None, allow_none=True)


def test_allowing_none_does_not_excuse_zero() -> None:
    with pytest.raises(ConfigurationError, match="size must be greater than zero"):
        check_positive("size", 0, allow_none=True)
