"""ORIGINAL, MKV and audio-only output: planning, the FFmpeg command and whole downloads."""

from pathlib import Path

import httpx
import pytest

from rayohx import ContainerFormat, DownloadState, OutputFormat, RemuxBackend
from rayohx._download._output import audio_suffix, plan_output
from rayohx._mux.ffmpeg import FfmpegInput, build_command
from rayohx.config import DownloadConfig, NetworkConfig, OutputConfig, SelectionConfig
from rayohx.downloader import Downloader
from rayohx.enums import Processing
from rayohx.errors import OutputFormatError
from rayohx.serialization import result_to_dict
from tests.unit._mux.helpers import (
    Site,
    decodes_cleanly,
    hls_site,
    needs_ffmpeg,
    probe,
    single_file_site,
)

BASE = "https://media.example.com/"
TS, FMP4 = ContainerFormat.MPEG_TS, ContainerFormat.FMP4
URL = BASE + "show/index.m3u8"


def plan(requested: OutputFormat, name: str | None = None, **kw: object):  # type: ignore[no-untyped-def]
    path = Path("/out") / name if name else None
    return plan_output(
        path=path,
        requested=requested,
        container=kw.pop("container", TS),  # type: ignore[arg-type]
        url=URL,
        directory=Path("/out"),
        allow_remux=True,
        **kw,  # type: ignore[arg-type]
    )


# --- planning ----------------------------------------------------------------------------------


def test_original_keeps_the_streams_own_container() -> None:
    ts = plan(OutputFormat.ORIGINAL)
    assert (ts.path, ts.format, ts.mux, ts.via_ffmpeg) == (
        Path("/out/show.ts"),
        OutputFormat.TS,
        False,
        False,
    )
    fmp4 = plan(OutputFormat.ORIGINAL, container=FMP4)
    assert (fmp4.path, fmp4.format, fmp4.mux) == (Path("/out/show.mp4"), OutputFormat.MP4, False)
    assert plan(OutputFormat.ORIGINAL, "x").path == Path("/out/x.ts")
    assert plan(OutputFormat.ORIGINAL, "x.m2ts").path == Path("/out/x.m2ts")


def test_original_refuses_what_would_change_the_container() -> None:
    with pytest.raises(OutputFormatError, match="own format"):
        plan(OutputFormat.ORIGINAL, "x.mp4")
    with pytest.raises(OutputFormatError, match="separate audio"):
        plan(OutputFormat.ORIGINAL, merge=True)


def test_mkv_needs_ffmpeg_and_follows_the_name() -> None:
    for container in (TS, FMP4):
        mkv = plan(OutputFormat.MKV, container=container)
        assert (mkv.path, mkv.format, mkv.mux, mkv.via_ffmpeg) == (
            Path("/out/show.mkv"), OutputFormat.MKV, True, True,
        )  # fmt: skip
    assert plan(OutputFormat.MKV, "film").path == Path("/out/film.mkv")
    assert plan(OutputFormat.MKV, "film.mkv", merge=True).path == Path("/out/film.mkv")
    auto = plan(OutputFormat.AUTO, "film.mkv")
    assert (auto.format, auto.via_ffmpeg) == (OutputFormat.MKV, True)
    with pytest.raises(OutputFormatError, match=r"ends in '\.mp4'"):
        plan(OutputFormat.MKV, "film.mp4")
    with pytest.raises(OutputFormatError, match=r"ends in '\.mkv'"):
        plan(OutputFormat.MP4, "film.mkv")


def test_audio_keeps_a_given_extension_and_defers_the_rest() -> None:
    fixed = plan(OutputFormat.AUDIO, "song.mp3")
    assert (fixed.path, fixed.suffix_pending, fixed.via_ffmpeg) == (
        Path("/out/song.mp3"),
        False,
        True,
    )
    pending = plan(OutputFormat.AUDIO, "song")
    assert (pending.path, pending.suffix_pending) == (Path("/out/song.mka"), True)
    unnamed = plan(OutputFormat.AUDIO)
    assert unnamed.path == Path("/out/show.mka")
    assert plan(OutputFormat.AUTO, "song.aac").format is OutputFormat.AUDIO
    assert plan(OutputFormat.AUTO, "song.m4a").format is OutputFormat.MP4  # unchanged for AUTO
    with pytest.raises(OutputFormatError, match="not an audio file"):
        plan(OutputFormat.AUDIO, "song.wav")


@pytest.mark.parametrize(
    ("codecs", "container", "suffix"),
    [
        (("aac",), TS, ".m4a"),
        (("mp3",), TS, ".mp3"),
        (("ac3",), TS, ".ac3"),
        (("eac3",), TS, ".eac3"),
        (("weird",), TS, ".mka"),
        ((), TS, ".mka"),
        ((), FMP4, ".m4a"),
    ],
)
def test_the_audio_extension_follows_the_codec(
    codecs: tuple[str, ...], container: ContainerFormat, suffix: str
) -> None:
    assert audio_suffix(codecs, container) == suffix


# --- the FFmpeg command ------------------------------------------------------------------------


def command(output: str, **kw: object) -> list[str]:
    inputs = [FfmpegInput(Path("v.ts"), ("aac",)), FfmpegInput(Path("a.ts"), ("aac",), "en")]
    return build_command(Path("ffmpeg"), inputs, Path(output), **kw)  # type: ignore[arg-type]


def test_matroska_is_copied_without_mp4_options() -> None:
    cmd = command("out.mkv", kind="mkv")
    assert cmd[-3:] == ["-f", "matroska", "out.mkv"]
    assert "-movflags" not in cmd
    assert cmd[cmd.index("-c") + 1] == "copy"
    assert "0:v?" in cmd
    assert cmd.count("aac_adtstoasc") == 2


def test_the_default_command_is_still_a_fragmented_mp4() -> None:
    cmd = command("out.mp4")
    assert (
        cmd[-5:-1]
        == ["-movflags", "frag_keyframe+empty_moov+delay_moov+default_base_moof", "-f", "mp4"][:4]
    )


@pytest.mark.parametrize(
    ("suffix", "muxer", "fixes_aac"),
    [
        (".m4a", "mp4", True),
        (".mka", "matroska", True),
        (".aac", "adts", False),
        (".mp3", "mp3", False),
    ],
)
def test_audio_commands_drop_video_and_pick_the_muxer(
    suffix: str, muxer: str, fixes_aac: bool
) -> None:
    cmd = command(f"out{suffix}", kind="mp4", audio_only=True)
    assert "-vn" in cmd
    assert not any(a.endswith(":v?") for a in cmd)
    assert cmd[-3:] == ["-f", muxer, f"out{suffix}"] or cmd[-3:-1] == ["-f", muxer]
    assert ("aac_adtstoasc" in cmd) is fixes_aac
    assert ("+faststart" in cmd) is (muxer == "mp4")


# --- whole downloads ---------------------------------------------------------------------------


def run(site: Site, path: str, output: Path, fmt: OutputFormat, **kw: object) -> Downloader:
    config = DownloadConfig(
        network=NetworkConfig(retries=0, backoff_factor=0.001),
        output=OutputConfig(format=fmt, remux_backend=kw.pop("backend", RemuxBackend.AUTO)),  # type: ignore[arg-type]
        selection=kw.pop("selection", SelectionConfig()),  # type: ignore[arg-type]
    )
    return Downloader(
        BASE + path, output=output, config=config, transport=httpx.MockTransport(site)
    )


def hidden(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir() if p.name.startswith("."))


def test_original_saves_a_transport_stream_as_it_came(tmp_path: Path) -> None:
    site = single_file_site("h264_aac.ts")
    result = run(site, "show/index.m3u8", tmp_path / "clip", OutputFormat.ORIGINAL).run()
    assert result.success, result.error
    assert result.output is not None
    assert result.output.path == tmp_path / "clip.ts"
    assert result.output.processing is Processing.COPIED
    assert result.output.container is ContainerFormat.MPEG_TS


def test_original_refuses_separate_audio_before_downloading(tmp_path: Path) -> None:
    site = hls_site("ts", "ts")
    result = run(site, "ts/master.m3u8", tmp_path / "m", OutputFormat.ORIGINAL).run()
    assert result.state is DownloadState.FAILED
    assert "separate audio" in (result.error or "")
    assert not [p for p in site.log if p.endswith(".ts")]


@pytest.mark.parametrize("fmt", [OutputFormat.MKV, OutputFormat.AUDIO])
def test_ffmpeg_formats_fail_early_without_ffmpeg(
    tmp_path: Path, fmt: OutputFormat, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("rayohx.downloader.controller.find_ffmpeg", lambda _path=None: None)
    site = single_file_site("h264_aac.ts")
    result = run(site, "show/index.m3u8", tmp_path / "x", fmt).run()
    assert result.state is DownloadState.FAILED
    assert "needs FFmpeg" in (result.error or "")
    assert "install it" in (result.error or "")
    assert not [p for p in site.log if p.endswith(".ts")]  # nothing was downloaded
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("fmt", [OutputFormat.MKV, OutputFormat.AUDIO])
def test_the_native_only_setting_refuses_ffmpeg_formats(tmp_path: Path, fmt: OutputFormat) -> None:
    site = single_file_site("h264_aac.ts")
    result = run(site, "show/index.m3u8", tmp_path / "x", fmt, backend=RemuxBackend.NATIVE).run()
    assert result.state is DownloadState.FAILED
    assert "only the built-in remuxer" in (result.error or "")


@needs_ffmpeg
def test_a_transport_stream_becomes_matroska(tmp_path: Path) -> None:
    site = single_file_site("h264_aac.ts")
    result = run(site, "show/index.m3u8", tmp_path / "clip", OutputFormat.MKV).run()
    assert result.success, result.error
    assert result.output is not None
    assert result.output.path == tmp_path / "clip.mkv"
    assert (result.output.container, result.output.processing) == (
        ContainerFormat.MATROSKA, Processing.REMUXED,
    )  # fmt: skip
    streams = probe(tmp_path / "clip.mkv")
    assert (len(streams["video"]), len(streams["audio"])) == (1, 1)
    assert decodes_cleanly(tmp_path / "clip.mkv")
    assert hidden(tmp_path) == []
    assert result_to_dict(result)["output"]["processing"] == "remuxed"  # type: ignore[index]


@needs_ffmpeg
@pytest.mark.parametrize("kind", ["ts", "fmp4"])
def test_a_separate_audio_track_is_joined_into_matroska(tmp_path: Path, kind: str) -> None:
    site = hls_site(kind, kind)
    result = run(site, f"{kind}/master.m3u8", tmp_path / "movie.mkv", OutputFormat.AUTO).run()
    assert result.success, result.error
    assert result.output is not None
    assert result.output.processing is Processing.MUXED
    streams = probe(tmp_path / "movie.mkv")
    assert (len(streams["video"]), len(streams["audio"])) == (1, 1)
    assert hidden(tmp_path) == []


@needs_ffmpeg
def test_audio_is_taken_out_of_a_transport_stream(tmp_path: Path) -> None:
    site = single_file_site("h264_aac.ts")
    result = run(site, "show/index.m3u8", tmp_path / "talk", OutputFormat.AUDIO).run()
    assert result.success, result.error
    assert result.output is not None
    assert result.output.path == tmp_path / "talk.m4a"
    assert (result.output.container, result.output.processing) == (
        ContainerFormat.AUDIO, Processing.EXTRACTED,
    )  # fmt: skip
    streams = probe(tmp_path / "talk.m4a")
    assert (len(streams["video"]), len(streams["audio"])) == (0, 1)
    assert hidden(tmp_path) == []


@needs_ffmpeg
def test_audio_only_from_a_separate_track_never_fetches_the_video(tmp_path: Path) -> None:
    site = hls_site("ts", "ts")
    result = run(site, "ts/master.m3u8", tmp_path / "radio", OutputFormat.AUDIO).run()
    assert result.success, result.error
    assert result.output is not None
    assert result.output.path.suffix == ".m4a"
    assert (len(probe(result.output.path)["video"]), len(probe(result.output.path)["audio"])) == (
        0,
        1,
    )
    segments = {p for p in site.log if p.endswith(".ts")}
    assert segments == {"ts/v1_0.ts", "ts/v1_1.ts", "ts/v1_2.ts"}  # the audio playlist only
    assert not any(p.startswith("ts/v0_") for p in site.log)


@needs_ffmpeg
def test_a_named_audio_extension_is_respected(tmp_path: Path) -> None:
    site = single_file_site("h264_aac.ts")
    result = run(site, "show/index.m3u8", tmp_path / "talk.mka", OutputFormat.AUDIO).run()
    assert result.success, result.error
    assert result.output is not None
    assert result.output.path == tmp_path / "talk.mka"
    assert len(probe(result.output.path)["audio"]) == 1
