import dataclasses

import pytest

from rayohx.models import Resolution, Variant

URI = "https://example.com/low.m3u8"


def test_a_variant_needs_only_an_address_and_a_bandwidth() -> None:
    variant = Variant(uri=URI, bandwidth=800_000)
    assert (variant.uri, variant.bandwidth) == (URI, 800_000)
    assert variant.average_bandwidth is None
    assert variant.resolution is None
    assert variant.codecs == ()
    assert variant.frame_rate is None
    assert variant.name is None
    assert (variant.video_group, variant.audio_group, variant.subtitle_group) == (None,) * 3


def test_the_height_comes_from_the_resolution() -> None:
    variant = Variant(uri=URI, bandwidth=1, resolution=Resolution(1280, 720))
    assert variant.height == 720


def test_the_height_is_unknown_without_a_resolution() -> None:
    assert Variant(uri=URI, bandwidth=1).height is None


def test_codecs_given_as_a_list_are_kept_as_a_tuple() -> None:
    variant = Variant(uri=URI, bandwidth=1, codecs=["avc1.42e01e", "mp4a.40.2"])  # type: ignore[arg-type]
    assert variant.codecs == ("avc1.42e01e", "mp4a.40.2")


def test_a_negative_bandwidth_is_refused_but_zero_is_not() -> None:
    with pytest.raises(ValueError, match="bandwidth must not be negative"):
        Variant(uri=URI, bandwidth=-1)
    assert Variant(uri=URI, bandwidth=0).bandwidth == 0


def test_a_variant_cannot_be_changed() -> None:
    variant = Variant(uri=URI, bandwidth=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        variant.bandwidth = 2  # type: ignore[misc]


def test_arguments_must_be_named() -> None:
    with pytest.raises(TypeError):
        Variant(URI, 1)  # type: ignore[call-arg]


def test_variants_with_the_same_values_are_equal_and_hash_alike() -> None:
    first = Variant(uri=URI, bandwidth=1, resolution=Resolution(640, 360), codecs=["a"])  # type: ignore[arg-type]
    second = Variant(uri=URI, bandwidth=1, resolution=Resolution(640, 360), codecs=("a",))
    assert first == second
    assert hash(first) == hash(second)
    assert first != Variant(uri=URI, bandwidth=2)
