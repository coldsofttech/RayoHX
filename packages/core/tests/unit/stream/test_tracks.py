import pytest

from rayohx import AudioTrack, MasterPlaylist, SubtitleTrack
from rayohx.config import SelectionConfig
from rayohx.stream import select_stream
from rayohx.stream._tracks import _language_matches, select_audio, select_subtitles
from tests.helpers.hls import BASE, variant
from tests.helpers.hls import master as load


def audio(config: SelectionConfig) -> tuple[list[str], tuple[str, ...]]:
    chosen = select_stream(load("master_audio_subs.m3u8"), config)
    return [track.name for track in chosen.audio_tracks], chosen.notes


def subtitles(config: SelectionConfig) -> tuple[list[str], tuple[str, ...]]:
    chosen = select_stream(load("master_audio_subs.m3u8"), config)
    return [track.name for track in chosen.subtitle_tracks], chosen.notes


def test_audio_language_selection() -> None:
    assert audio(SelectionConfig(audio_languages=("fr",))) == (["Français"], ())
    assert audio(SelectionConfig(audio_languages=("en",)))[0] == ["English"]


def test_several_audio_languages_keep_the_requested_order() -> None:
    names, notes = audio(SelectionConfig(audio_languages=("fr", "en")))
    assert names == ["Français", "English"]
    assert notes == ()


def test_a_main_language_matches_its_regional_variant() -> None:
    assert audio(SelectionConfig(audio_languages=("de",)))[0] == ["Deutsch"]
    assert audio(SelectionConfig(audio_languages=("de-DE",)))[0] == ["Deutsch"]
    names, notes = audio(SelectionConfig(audio_languages=("de-AT",)))
    assert names == ["English"]
    assert notes


def test_an_unavailable_audio_language_falls_back_to_the_default_with_notes() -> None:
    names, notes = audio(SelectionConfig(audio_languages=("pt",)))
    assert names == ["English"]
    assert any("'pt'" in note for note in notes)
    assert any("default audio track" in note for note in notes)


def test_a_partly_available_audio_list_keeps_what_exists() -> None:
    names, notes = audio(SelectionConfig(audio_languages=("fr", "pt")))
    assert names == ["Français"]
    assert len(notes) == 1


def test_audio_tracks_can_be_chosen_by_name() -> None:
    names, _ = audio(SelectionConfig(audio_names=("english commentary",)))
    assert names == ["English Commentary"]
    names, notes = audio(SelectionConfig(audio_names=("Klingon",)))
    assert names == ["English"]
    assert any("Klingon" in note for note in notes)


def test_subtitles_are_off_unless_requested() -> None:
    assert subtitles(SelectionConfig())[0] == []


def test_subtitle_language_selection_prefers_unforced_tracks() -> None:
    assert subtitles(SelectionConfig(subtitle_languages=("en",)))[0] == ["English"]
    names, _ = subtitles(SelectionConfig(subtitle_languages=("es", "en")))
    assert names == ["Español", "English"]
    names, _ = subtitles(SelectionConfig(subtitle_names=("English (forced)",)))
    assert names == ["English (forced)"]


def test_an_unavailable_subtitle_language_selects_nothing_and_says_so() -> None:
    names, notes = subtitles(SelectionConfig(subtitle_languages=("ja",)))
    assert names == []
    assert any("'ja'" in note for note in notes)


def test_streams_without_tracks_say_so() -> None:
    chosen = select_stream(
        load("master_basic.m3u8"),
        SelectionConfig(audio_languages=("en",), subtitle_languages=("en",)),
    )
    assert chosen.audio_tracks == ()
    assert chosen.subtitle_tracks == ()
    assert len(chosen.notes) == 2


def test_audio_that_is_part_of_the_video_needs_no_separate_download() -> None:
    muxed = AudioTrack(group_id="a", name="Main", language="en", uri=None, default=True)
    master = MasterPlaylist(
        uri=BASE,
        variants=(variant(1000, (1280, 720), uri="v", audio_group="a"),),
        audio_tracks=(muxed,),
    )
    chosen = select_stream(master, SelectionConfig())
    assert chosen.audio_tracks == ()
    assert chosen.notes == ()


def test_language_matching_ignores_case() -> None:
    master = MasterPlaylist(
        uri=BASE,
        variants=(variant(1000, (1280, 720), uri="v", audio_group="a", subtitle_group="s"),),
        audio_tracks=(AudioTrack(group_id="a", name="Eng", language="EN", uri="a.m3u8"),),
        subtitle_tracks=(SubtitleTrack(group_id="s", name="Sub", language="En-us", uri="s.m3u8"),),
    )
    chosen = select_stream(
        master, SelectionConfig(audio_languages=("en",), subtitle_languages=("en-US",))
    )
    assert [track.name for track in chosen.audio_tracks] == ["Eng"]
    assert [track.name for track in chosen.subtitle_tracks] == ["Sub"]


# --- the pieces, one at a time -----------------------------------------------------------------


def master_with(
    audio: tuple[AudioTrack, ...] = (), subtitles: tuple[SubtitleTrack, ...] = ()
) -> MasterPlaylist:
    stream = variant(1000, (1280, 720), uri="v", audio_group="a", subtitle_group="s")
    return MasterPlaylist(
        uri=BASE, variants=(stream,), audio_tracks=audio, subtitle_tracks=subtitles
    )


def audio_named(
    master: MasterPlaylist, config: SelectionConfig | None = None
) -> tuple[list[str], list[str]]:
    notes: list[str] = []
    tracks = select_audio(master, master.variants[0], config or SelectionConfig(), notes)
    return [track.name for track in tracks], notes


def subtitles_named(master: MasterPlaylist, config: SelectionConfig) -> tuple[list[str], list[str]]:
    notes: list[str] = []
    tracks = select_subtitles(master, master.variants[0], config, notes)
    return [track.name for track in tracks], notes


@pytest.mark.parametrize(
    ("wanted", "offered", "score"),
    [
        ("en", "en", 2),
        ("EN_us", "en-US", 2),
        (" en ", "EN", 2),
        ("de", "de-DE", 1),
        ("de-DE", "de", 1),
        ("de-AT", "de-DE", 0),
        ("en", "fr", 0),
        ("en", None, 0),
        ("en", "", 0),
    ],
)
def test_how_well_a_language_matches(wanted: str, offered: str | None, score: int) -> None:
    assert _language_matches(wanted, offered) == score


def test_a_stream_without_an_audio_group_has_no_separate_audio() -> None:
    master = MasterPlaylist(uri=BASE, variants=(variant(1000, (1280, 720), uri="v"),))
    assert audio_named(master) == ([], [])
    names, notes = audio_named(master, SelectionConfig(audio_languages=("en",)))
    assert names == []
    assert any("built-in audio" in note for note in notes)


def test_the_default_track_is_used_when_nothing_is_asked_for() -> None:
    master = master_with(
        audio=(
            AudioTrack(group_id="a", name="Other", uri="o.m3u8"),
            AudioTrack(group_id="a", name="Main", uri="m.m3u8", default=True),
        )
    )
    assert audio_named(master) == (["Main"], [])


def test_autoselect_comes_next_when_no_track_is_the_default() -> None:
    master = master_with(
        audio=(
            AudioTrack(group_id="a", name="Plain", uri="p.m3u8"),
            AudioTrack(group_id="a", name="Auto", uri="a.m3u8", autoselect=True),
        )
    )
    assert audio_named(master)[0] == ["Auto"]


def test_a_forced_track_is_the_last_choice() -> None:
    master = master_with(
        audio=(
            AudioTrack(group_id="a", name="Forced", uri="f.m3u8", default=True, forced=True),
            AudioTrack(group_id="a", name="Plain", uri="p.m3u8"),
        )
    )
    assert audio_named(master)[0] == ["Plain"]


def test_the_first_listed_track_wins_a_tie() -> None:
    master = master_with(
        audio=(
            AudioTrack(group_id="a", name="First", uri="1.m3u8"),
            AudioTrack(group_id="a", name="Second", uri="2.m3u8"),
        )
    )
    assert audio_named(master)[0] == ["First"]


def test_a_track_inside_the_video_is_not_downloaded_separately() -> None:
    master = master_with(audio=(AudioTrack(group_id="a", name="Muxed", default=True),))
    assert audio_named(master) == ([], [])


def test_names_are_chosen_before_languages() -> None:
    master = master_with(
        audio=(
            AudioTrack(group_id="a", name="A", language="en", uri="a.m3u8"),
            AudioTrack(group_id="a", name="B", language="fr", uri="b.m3u8"),
        )
    )
    config = SelectionConfig(audio_names=("B",), audio_languages=("en",))
    assert audio_named(master, config)[0] == ["B", "A"]


def test_a_track_asked_for_twice_is_chosen_once() -> None:
    master = master_with(audio=(AudioTrack(group_id="a", name="A", language="en", uri="a.m3u8"),))
    config = SelectionConfig(audio_names=("a",), audio_languages=("en",))
    assert audio_named(master, config) == (["A"], [])


def test_subtitles_that_were_not_asked_for_are_not_selected() -> None:
    master = master_with(
        subtitles=(SubtitleTrack(group_id="s", name="English", language="en", uri="e.m3u8"),)
    )
    assert subtitles_named(master, SelectionConfig()) == ([], [])


def test_asking_for_subtitles_the_stream_does_not_have_is_explained() -> None:
    config = SelectionConfig(subtitle_languages=("en",))
    names, notes = subtitles_named(master_with(), config)
    assert names == []
    assert notes == ["The stream has no subtitle tracks."]
    no_group = MasterPlaylist(uri=BASE, variants=(variant(1000, (1280, 720), uri="v"),))
    assert subtitles_named(no_group, config)[1] == ["The stream has no subtitle tracks."]


def test_a_subtitle_track_is_chosen_by_language_and_needs_its_own_address() -> None:
    master = master_with(
        subtitles=(
            SubtitleTrack(group_id="s", name="Burned in", language="en"),
            SubtitleTrack(group_id="s", name="English", language="fr", uri="e.m3u8"),
        )
    )
    assert subtitles_named(master, SelectionConfig(subtitle_languages=("fr",)))[0] == ["English"]
    assert subtitles_named(master, SelectionConfig(subtitle_languages=("en",))) == (
        [],
        [],
    )
