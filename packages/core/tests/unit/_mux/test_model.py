import dataclasses

import pytest

from rayohx._mux._model import Sample, TrackConfig


def test_a_track_needs_only_what_every_kind_has() -> None:
    config = TrackConfig("audio", 44100, b"entry", "mp4a.40.2")
    assert (config.kind, config.timescale, config.sample_entry, config.codec) == (
        "audio",
        44100,
        b"entry",
        "mp4a.40.2",
    )
    assert (config.width, config.height, config.channels, config.sample_rate) == (0, 0, 0, 0)
    assert config.language == "und"
    assert config.name == ""


def test_a_track_description_cannot_be_changed() -> None:
    config = TrackConfig("video", 90000, b"x", "avc1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.width = 1  # type: ignore[misc]


def test_equal_track_descriptions_are_the_same_dictionary_key() -> None:
    first = TrackConfig("video", 90000, b"x", "avc1", width=16, height=16)
    second = TrackConfig("video", 90000, b"x", "avc1", width=16, height=16)
    assert first == second
    assert len({first, second}) == 1
    assert first != TrackConfig("video", 90000, b"x", "avc1", width=32, height=16)


def test_a_sample_is_a_keyframe_without_a_composition_offset_by_default() -> None:
    sample = Sample(b"data", dts=10, duration=5)
    assert sample.sync is True
    assert sample.cts_offset == 0


def test_a_samples_timing_can_be_filled_in_later() -> None:
    sample = Sample(b"data", dts=10, duration=0)
    sample.duration = 40
    sample.dts -= 4
    assert (sample.dts, sample.duration) == (6, 40)


def test_a_sample_has_no_room_for_stray_attributes() -> None:
    sample = Sample(b"data", dts=0, duration=1)
    with pytest.raises(AttributeError):
        sample.durration = 2  # type: ignore[attr-defined]
