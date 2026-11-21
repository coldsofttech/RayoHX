import dataclasses

import pytest

from rayohx.models import AudioTrack, SubtitleTrack, VideoTrack


def test_an_audio_track_needs_only_a_group_and_a_name() -> None:
    track = AudioTrack(group_id="aud", name="English")
    assert (track.group_id, track.name) == ("aud", "English")
    assert track.language is None
    assert track.uri is None  # the audio is inside the video segments
    assert (track.default, track.autoselect, track.forced) == (False, False, False)
    assert track.channels is None
    assert track.characteristics == ()


def test_a_subtitle_track_needs_only_a_group_and_a_name() -> None:
    track = SubtitleTrack(group_id="sub", name="English")
    assert (track.group_id, track.name) == ("sub", "English")
    assert track.language is None
    assert track.uri is None
    assert (track.default, track.autoselect, track.forced) == (False, False, False)
    assert track.characteristics == ()


def test_a_video_track_needs_only_a_group_and_a_name() -> None:
    track = VideoTrack(group_id="vid", name="Angle 2")
    assert (track.group_id, track.name) == ("vid", "Angle 2")
    assert track.uri is None
    assert (track.default, track.autoselect) == (False, False)


def test_a_video_track_has_no_language_or_forced_flag() -> None:
    track = VideoTrack(group_id="vid", name="Angle 2")
    assert not hasattr(track, "language")
    assert not hasattr(track, "forced")


@pytest.mark.parametrize(
    "make",
    [
        lambda: AudioTrack(group_id="a", name="n"),
        lambda: SubtitleTrack(group_id="s", name="n"),
        lambda: VideoTrack(group_id="v", name="n"),
    ],
)
def test_tracks_cannot_be_changed(make) -> None:  # type: ignore[no-untyped-def]
    track = make()
    with pytest.raises(dataclasses.FrozenInstanceError):
        track.name = "other"


@pytest.mark.parametrize("track_type", [AudioTrack, SubtitleTrack, VideoTrack])
def test_arguments_must_be_named(track_type: type) -> None:
    with pytest.raises(TypeError):
        track_type("group", "name")


@pytest.mark.parametrize("track_type", [AudioTrack, SubtitleTrack, VideoTrack])
def test_a_group_and_a_name_cannot_be_left_out(track_type: type) -> None:
    with pytest.raises(TypeError):
        track_type(group_id="group")
    with pytest.raises(TypeError):
        track_type(name="name")


def test_tracks_with_the_same_values_are_equal() -> None:
    first = AudioTrack(group_id="a", name="English", language="en", default=True)
    second = AudioTrack(group_id="a", name="English", language="en", default=True)
    assert first == second
    assert first != AudioTrack(group_id="a", name="English", language="fr", default=True)
    assert first != SubtitleTrack(  # type: ignore[comparison-overlap]
        group_id="a", name="English", language="en", default=True
    )
