from pathlib import Path

import pytest

from rayohx._download._output import OutputPlan
from rayohx.config import DownloadConfig, OutputConfig
from rayohx.downloader._prepare import choose_backend, load_renditions, load_subtitle_jobs
from rayohx.enums import ContainerFormat, EventType, OutputFormat, RemuxBackend
from rayohx.errors import OutputFormatError
from rayohx.models import AudioTrack, SubtitleTrack
from rayohx.stream import StreamSelection
from tests.helpers.media import BASE
from tests.unit.downloader.test_stream import (
    FakeClient,
    audio_track,
    master_playlist,
    media_playlist,
    subtitle_track,
)

AUDIO = BASE + "en.m3u8"
SUBTITLES = BASE + "en-sub.m3u8"
TS_PLAYLIST = "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:2,\na.ts\n"
VTT_PLAYLIST = "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:2,\na.vtt\n"
VARIABLE_PLAYLIST = (
    '#EXTM3U\n#EXT-X-DEFINE:IMPORT="host"\n#EXT-X-TARGETDURATION:2\n#EXTINF:2,\n'
    "https://{$host}/a.ts\n"
)


class Recorder:
    """Stands in for the downloader's event emitter."""

    def __init__(self) -> None:
        self.events: list[tuple[EventType, dict[str, object]]] = []

    def __call__(self, kind: EventType, *, data: dict[str, object] | None = None) -> None:
        self.events.append((kind, data or {}))


def selection(
    audio: tuple[AudioTrack, ...] = (), subtitles: tuple[SubtitleTrack, ...] = ()
) -> StreamSelection:
    return StreamSelection(
        variant=master_playlist().variants[0], audio_tracks=audio, subtitle_tracks=subtitles
    )


def plan(tmp_path: Path, *, mux: bool) -> OutputPlan:
    return OutputPlan(
        path=tmp_path / "out.mp4",
        format=OutputFormat.MP4,
        container=ContainerFormat.MPEG_TS,
        mux=mux,
    )


# --- audio tracks ------------------------------------------------------------------------------


def test_no_selection_has_no_audio_tracks() -> None:
    assert load_renditions(FakeClient(), None, None, Recorder()) == []  # type: ignore[arg-type]


def test_an_audio_track_is_loaded_and_reported() -> None:
    client = FakeClient(texts={AUDIO: TS_PLAYLIST})
    emit = Recorder()
    renditions = load_renditions(client, selection(audio=(audio_track(),)), None, emit)  # type: ignore[arg-type]
    assert [(r.track.name, r.container) for r in renditions] == [
        ("English", ContainerFormat.MPEG_TS)
    ]
    assert emit.events == [(EventType.PLAYLIST_LOADED, {"kind": "media", "audio": "English"})]


def test_an_audio_track_gets_the_master_variables() -> None:
    client = FakeClient(texts={AUDIO: VARIABLE_PLAYLIST})
    renditions = load_renditions(
        client,  # type: ignore[arg-type]
        selection(audio=(audio_track(),)),
        {"host": "cdn.example.com"},
        Recorder(),
    )
    assert renditions[0].media.segments[0].uri == "https://cdn.example.com/a.ts"


def test_an_audio_track_that_cannot_be_joined_is_refused() -> None:
    client = FakeClient(texts={AUDIO: VTT_PLAYLIST})
    with pytest.raises(OutputFormatError, match="cannot be joined in") as info:
        load_renditions(client, selection(audio=(audio_track(),)), None, Recorder())  # type: ignore[arg-type]
    assert info.value.hint


# --- subtitle tracks ---------------------------------------------------------------------------


def test_no_selection_has_no_subtitle_jobs(tmp_path: Path) -> None:
    jobs = load_subtitle_jobs(FakeClient(), None, plan(tmp_path, mux=False), None, Recorder())  # type: ignore[arg-type]
    assert jobs == []


def test_a_subtitle_track_is_saved_beside_the_video(tmp_path: Path) -> None:
    client = FakeClient(texts={SUBTITLES: VTT_PLAYLIST})
    emit = Recorder()
    jobs = load_subtitle_jobs(
        client,  # type: ignore[arg-type]
        selection(subtitles=(subtitle_track(),)),
        plan(tmp_path, mux=False),
        None,
        emit,
    )
    assert [path.parent for _, _, path in jobs] == [tmp_path]
    assert emit.events == [(EventType.PLAYLIST_LOADED, {"kind": "media", "subtitles": "English"})]


def test_subtitles_that_are_not_text_are_refused(tmp_path: Path) -> None:
    client = FakeClient(texts={SUBTITLES: TS_PLAYLIST})
    with pytest.raises(OutputFormatError, match="not WebVTT") as info:
        load_subtitle_jobs(
            client,  # type: ignore[arg-type]
            selection(subtitles=(subtitle_track(),)),
            plan(tmp_path, mux=False),
            None,
            Recorder(),
        )
    assert info.value.hint


# --- remux backend -----------------------------------------------------------------------------


def test_a_plain_join_needs_no_backend(tmp_path: Path) -> None:
    config = DownloadConfig()
    result = choose_backend(
        FakeClient(),  # type: ignore[arg-type]
        media_playlist("a.ts"),
        ContainerFormat.MPEG_TS,
        [],
        plan(tmp_path, mux=False),
        config,
    )
    assert result is None


def test_a_missing_ffmpeg_is_explained_when_it_was_asked_for(tmp_path: Path) -> None:
    config = DownloadConfig(
        output=OutputConfig(
            remux_backend=RemuxBackend.FFMPEG, ffmpeg_path=tmp_path / "missing-ffmpeg"
        )
    )
    with pytest.raises(OutputFormatError, match="FFmpeg was asked for") as info:
        choose_backend(
            FakeClient(),  # type: ignore[arg-type]
            media_playlist("a.ts"),
            ContainerFormat.MPEG_TS,
            [],
            plan(tmp_path, mux=True),
            config,
        )
    assert info.value.hint
