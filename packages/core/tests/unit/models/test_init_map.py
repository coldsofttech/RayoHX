import dataclasses

import pytest

from rayohx.models import InitMap, SegmentRange

URI = "https://example.com/init.mp4"


def test_an_init_map_may_cover_the_whole_resource() -> None:
    init = InitMap(URI)
    assert init.uri == URI
    assert init.byte_range is None


def test_an_init_map_may_cover_a_byte_range() -> None:
    init = InitMap(URI, SegmentRange(720, 0))
    assert init.byte_range == SegmentRange(720, 0)


def test_an_init_map_cannot_be_changed() -> None:
    init = InitMap(URI)
    with pytest.raises(dataclasses.FrozenInstanceError):
        init.uri = "other"  # type: ignore[misc]


def test_equal_init_maps_are_the_same_dictionary_key() -> None:
    # The fetcher keeps each downloaded init section under its map, so segments that share one
    # map download it once.
    first = InitMap(URI, SegmentRange(720, 0))
    second = InitMap(URI, SegmentRange(720, 0))
    cache = {first: b"init"}
    assert cache[second] == b"init"
    assert InitMap(URI) not in cache
    assert InitMap(URI, SegmentRange(720, 10)) not in cache
