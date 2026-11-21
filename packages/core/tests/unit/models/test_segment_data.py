import dataclasses

import pytest

from rayohx.models import SegmentData


def test_a_segment_without_an_init_section_adds_only_its_media() -> None:
    data = SegmentData(index=3, media=b"x" * 10)
    assert data.init == b""
    assert data.size == 10


def test_the_init_section_counts_towards_the_size() -> None:
    assert SegmentData(index=0, media=b"x" * 10, init=b"y" * 4).size == 14


def test_an_empty_segment_has_no_size() -> None:
    assert SegmentData(index=0, media=b"").size == 0


def test_segment_data_cannot_be_changed() -> None:
    data = SegmentData(index=0, media=b"x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        data.media = b"y"  # type: ignore[misc]


def test_arguments_must_be_named() -> None:
    with pytest.raises(TypeError):
        SegmentData(0, b"x")  # type: ignore[call-arg]
