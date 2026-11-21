import dataclasses

import pytest

from rayohx.config import SelectionConfig
from rayohx.stream import StreamSelection, quality_height, select_stream
from tests.helpers.hls import master as load
from tests.helpers.hls import variant


def test_selection_is_deterministic() -> None:
    master = load("master_audio_subs.m3u8")
    first = select_stream(master, SelectionConfig(quality="best"))
    for _ in range(5):
        assert select_stream(master, SelectionConfig(quality="best")) == first


def test_default_selection_is_the_best_video_with_the_default_audio_and_no_subtitles() -> None:
    chosen = select_stream(load("master_audio_subs.m3u8"), SelectionConfig())
    assert quality_height(chosen.variant) == 1080
    assert [track.name for track in chosen.audio_tracks] == ["English"]
    assert chosen.subtitle_tracks == ()
    assert chosen.notes == ()


def test_video_only_skips_audio_and_subtitle_tracks() -> None:
    master = load("master_audio_subs.m3u8")
    wanted = SelectionConfig(audio_languages=("fr",), subtitle_languages=("en",), video_only=True)
    chosen = select_stream(master, wanted)
    assert quality_height(chosen.variant) == 1080
    assert chosen.audio_tracks == ()
    assert chosen.subtitle_tracks == ()
    assert any("Only the video" in note for note in chosen.notes)
    assert SelectionConfig().as_dict()["video_only"] is False
    assert wanted.as_dict()["video_only"] is True


def test_a_selection_needs_only_a_variant() -> None:
    chosen = StreamSelection(variant=variant(1000, (1280, 720)))
    assert chosen.audio_tracks == ()
    assert chosen.subtitle_tracks == ()
    assert chosen.notes == ()


def test_a_selection_cannot_be_changed() -> None:
    chosen = StreamSelection(variant=variant(1000))
    with pytest.raises(dataclasses.FrozenInstanceError):
        chosen.notes = ("x",)  # type: ignore[misc]


def test_a_selection_is_made_of_named_arguments() -> None:
    with pytest.raises(TypeError):
        StreamSelection(variant(1000))  # type: ignore[call-arg]


def test_the_notes_explain_a_fallback() -> None:
    chosen = select_stream(load("master_basic.m3u8"), SelectionConfig(quality="240p"))
    assert quality_height(chosen.variant) == 360
    assert "240p" in chosen.notes[0]
