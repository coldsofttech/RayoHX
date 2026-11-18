"""Verification: the settings, checksums, strict segment checks and whole-download checks."""

import hashlib
from pathlib import Path

import httpx
import pytest

from rayohx import DownloadState, EventType, OutputFormat
from rayohx._download._containers import check_segment
from rayohx.config import DownloadConfig, NetworkConfig, OutputConfig, VerifyConfig
from rayohx.downloader import Downloader
from rayohx.enums import ContainerFormat, VerificationStatus, VerifyLevel
from rayohx.errors import ConfigurationError
from rayohx.events import DownloadEvent
from rayohx.serialization import result_to_dict
from rayohx.verify import CheckStatus, Expectations, file_checksum, verify_output
from tests.unit._mux.helpers import MEDIA, Site, hls_site, media, needs_ffmpeg, single_file_site

BASE = "https://media.example.com/"
TS_FILE = MEDIA / "h264_aac.ts"
TS, FMP4 = ContainerFormat.MPEG_TS, ContainerFormat.FMP4


# --- the settings ------------------------------------------------------------------------------


def test_nothing_is_requested_by_default() -> None:
    config = VerifyConfig()
    assert (config.level, config.checksum, config.expected_checksum) == (
        VerifyLevel.NONE,
        None,
        None,
    )
    assert not config.requested
    assert VerifyConfig(level="basic").requested
    assert VerifyConfig(checksum="sha256").requested


def test_the_checksum_algorithm_is_told_from_the_expected_value() -> None:
    for algorithm in ("md5", "sha1", "sha256", "sha512"):
        value = hashlib.new(algorithm, b"x").hexdigest().upper()
        config = VerifyConfig(expected_checksum=value)
        assert config.checksum == algorithm
        assert config.expected_checksum == value.lower()


@pytest.mark.parametrize(
    "bad",
    [
        {"checksum": "crc32"},
        {"expected_checksum": "xyz"},
        {"expected_checksum": "abcd"},
        {"checksum": "sha256", "expected_checksum": "a" * 40},
        {"level": "paranoid"},
    ],
)
def test_bad_settings_are_refused(bad: dict) -> None:
    with pytest.raises((ConfigurationError, ValueError)):
        VerifyConfig(**bad)


# --- checksums ---------------------------------------------------------------------------------


def test_a_checksum_is_the_files_digest(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    path.write_bytes(b"hello world" * 100_000)
    for algorithm in ("md5", "sha1", "sha256", "sha512"):
        expected = hashlib.new(algorithm, path.read_bytes()).hexdigest()
        assert file_checksum(path, algorithm) == expected
    with pytest.raises(ValueError, match="unsupported"):
        file_checksum(path, "crc32")


def test_no_checksum_is_calculated_unless_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "rayohx.verify.checks.file_checksum", lambda *a, **k: calls.append("hashed") or "x"
    )
    verify_output(
        TS_FILE, container=TS, config=VerifyConfig(level="strong"), expected=Expectations()
    )
    assert calls == []
    verify_output(
        TS_FILE, container=TS, config=VerifyConfig(checksum="sha256"), expected=Expectations()
    )
    assert calls == ["hashed"]


# --- strict segment checks ---------------------------------------------------------------------


def test_cut_off_segments_are_only_refused_when_strict() -> None:
    whole = media("h264_aac.ts")
    cut = whole[: 188 * 5 + 50]
    assert check_segment(TS, cut) is None
    assert "middle of a packet" in (check_segment(TS, cut, strict=True) or "")
    assert check_segment(TS, whole[: 188 * 5], strict=True) is None
    assert "not MPEG-TS" in (check_segment(TS, b"", strict=True) or "")


def fmp4_segment() -> bytes:
    return (
        (24).to_bytes(4, "big") + b"moof" + bytes(16)
        + (16).to_bytes(4, "big") + b"mdat" + bytes(8)
    )  # fmt: skip


def test_mp4_boxes_must_add_up_when_strict() -> None:
    whole = fmp4_segment()
    assert check_segment(FMP4, whole, strict=True) is None
    assert check_segment(FMP4, whole[:-3]) is None  # not noticed unless strict
    assert "cut off" in (check_segment(FMP4, whole[:-3], strict=True) or "")
    assert "cut off" in (check_segment(FMP4, whole + b"\x00\x00", strict=True) or "")
    assert check_segment(FMP4, whole + (0).to_bytes(4, "big") + b"free", strict=True) is None


# --- checking a finished file ------------------------------------------------------------------


def names(report) -> dict[str, CheckStatus]:  # type: ignore[no-untyped-def]
    return {c.name: c.status for c in report.checks}


def test_a_good_transport_stream_passes_basic_checks() -> None:
    report = verify_output(
        TS_FILE, container=TS, config=VerifyConfig(level="basic"), expected=Expectations(segments=3)
    )
    assert report.status is VerificationStatus.VERIFIED
    assert names(report) == {
        "output present": CheckStatus.PASSED,
        "container structure": CheckStatus.PASSED,
    }
    assert report.segments_checked == 3
    assert report.summary().startswith("Verified")
    assert report.media is None  # basic does not run ffprobe


def test_a_missing_empty_or_broken_file_fails(tmp_path: Path) -> None:
    config = VerifyConfig(level="basic")
    missing = verify_output(
        tmp_path / "no.ts", container=TS, config=config, expected=Expectations()
    )
    assert missing.status is VerificationStatus.FAILED
    assert "missing" in missing.summary()
    (tmp_path / "empty.ts").write_bytes(b"")
    assert (
        "empty"
        in verify_output(
            tmp_path / "empty.ts", container=TS, config=config, expected=Expectations()
        ).summary()
    )
    (tmp_path / "junk.ts").write_bytes(b"not video at all" * 100)
    junk = verify_output(tmp_path / "junk.ts", container=TS, config=config, expected=Expectations())
    assert junk.failures[0].name == "container structure"
    cut = tmp_path / "cut.mp4"
    cut.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 10)
    assert verify_output(cut, container=FMP4, config=config, expected=Expectations()).failures


def test_matroska_must_start_like_matroska(tmp_path: Path) -> None:
    config = VerifyConfig(level="basic")
    good = tmp_path / "a.mkv"
    good.write_bytes(b"\x1a\x45\xdf\xa3" + b"\x00" * 50)
    bad = tmp_path / "b.mkv"
    bad.write_bytes(b"RIFF" + b"\x00" * 50)
    matroska = ContainerFormat.MATROSKA
    assert verify_output(good, container=matroska, config=config, expected=Expectations()).verified
    assert not verify_output(
        bad, container=matroska, config=config, expected=Expectations()
    ).verified


def test_a_folder_of_segments_is_counted(tmp_path: Path) -> None:
    folder = tmp_path / "parts"
    folder.mkdir()
    for i in range(3):
        (folder / f"segment-{i}.ts").write_bytes(b"x")
    config = VerifyConfig(level="basic", checksum="sha256")
    ok = verify_output(folder, container=TS, config=config, expected=Expectations(segments=3))
    assert ok.verified
    assert names(ok)["checksum"] is CheckStatus.SKIPPED
    short = verify_output(folder, container=TS, config=config, expected=Expectations(segments=5))
    assert "3 of 5" in short.summary()


def test_checksums_match_or_fail(tmp_path: Path) -> None:
    digest = hashlib.sha256(TS_FILE.read_bytes()).hexdigest()
    ok = verify_output(
        TS_FILE,
        container=TS,
        config=VerifyConfig(expected_checksum=digest),
        expected=Expectations(),
    )
    assert ok.verified
    assert ok.checksum is not None
    assert (ok.checksum.algorithm, ok.checksum.value, ok.checksum.matches) == (
        "sha256",
        digest,
        True,
    )
    wrong = verify_output(
        TS_FILE,
        container=TS,
        config=VerifyConfig(expected_checksum="0" * 64),
        expected=Expectations(),
    )
    assert wrong.status is VerificationStatus.FAILED
    assert wrong.checksum is not None
    assert wrong.checksum.matches is False
    assert "not the expected" in wrong.summary()
    only = verify_output(
        TS_FILE, container=TS, config=VerifyConfig(checksum="md5"), expected=Expectations()
    )
    assert only.verified
    assert only.checksum is not None
    assert only.checksum.matches is None
    assert only.checks[0].name == "checksum"  # nothing else was asked for


@needs_ffmpeg
def test_strong_checks_look_inside_with_ffprobe() -> None:
    config = VerifyConfig(level="strong")
    report = verify_output(
        TS_FILE, container=TS, config=config, expected=Expectations(duration=4.0, audio=True)
    )
    assert report.verified, report.summary()
    assert names(report)["streams"] is CheckStatus.PASSED
    assert names(report)["duration"] is CheckStatus.PASSED
    assert report.media is not None
    assert report.media.of_kind("video")[0].codec == "h264"
    assert report.to_dict()["media"]["streams"]


@needs_ffmpeg
def test_strong_checks_catch_a_wrong_length_and_missing_streams() -> None:
    config = VerifyConfig(level="strong")
    short = verify_output(
        TS_FILE, container=TS, config=config, expected=Expectations(duration=120.0)
    )
    assert short.status is VerificationStatus.FAILED
    assert "playlist adds up to 120.0 s" in short.summary()
    audio_only = MEDIA / "aac_only.ts"
    no_video = verify_output(
        audio_only, container=TS, config=config, expected=Expectations(video=True)
    )
    assert "no video stream" in no_video.summary()
    fine = verify_output(
        audio_only, container=TS, config=config, expected=Expectations(video=False, audio=True)
    )
    assert fine.verified


def test_strong_without_ffprobe_skips_the_deep_check_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("rayohx.verify.checks.find_ffprobe", lambda _p=None: None)
    report = verify_output(
        TS_FILE, container=TS, config=VerifyConfig(level="strong"), expected=Expectations()
    )
    assert report.verified
    assert names(report)["deep inspection"] is CheckStatus.SKIPPED


@needs_ffmpeg
def test_a_truncated_file_that_still_has_a_header_fails_the_deep_check(tmp_path: Path) -> None:
    broken = tmp_path / "broken.ts"
    broken.write_bytes(TS_FILE.read_bytes()[: 188 * 8])  # whole packets, but almost no video
    report = verify_output(
        broken,
        container=TS,
        config=VerifyConfig(level="strong"),
        expected=Expectations(duration=4.0, audio=True),
    )
    assert report.status is VerificationStatus.FAILED


# --- whole downloads ---------------------------------------------------------------------------


def download(
    site: Site, output: Path, verify: VerifyConfig, **kw: object
) -> tuple[Downloader, list[DownloadEvent]]:
    config = DownloadConfig(
        network=NetworkConfig(retries=0, backoff_factor=0.001),
        output=OutputConfig(format=kw.pop("fmt", OutputFormat.AUTO)),  # type: ignore[arg-type]
        verify=verify,
    )
    downloader = Downloader(
        BASE + "show/index.m3u8", output=output, config=config, transport=httpx.MockTransport(site)
    )
    events: list[DownloadEvent] = []
    downloader.events.subscribe(events.append)
    return downloader, events


def test_a_download_without_verification_is_unchanged(tmp_path: Path) -> None:
    downloader, events = download(
        single_file_site("h264_aac.ts"), tmp_path / "a.ts", VerifyConfig()
    )
    result = downloader.run()
    assert result.success
    assert result.integrity is None
    assert DownloadState.VERIFYING not in {e.state for e in events}
    assert result_to_dict(result)["integrity"] is None


def test_a_verified_download_goes_through_the_verifying_state(tmp_path: Path) -> None:
    downloader, events = download(
        single_file_site("h264_aac.ts"), tmp_path / "a.ts", VerifyConfig(level="basic")
    )
    result = downloader.run()
    assert result.success, result.error
    assert result.integrity is not None
    assert result.integrity.verified
    kinds = [e.type for e in events]
    assert kinds.index(EventType.FINALIZATION_COMPLETED) < kinds.index(
        EventType.VERIFICATION_STARTED
    )
    assert kinds.index(EventType.VERIFICATION_STARTED) < kinds.index(
        EventType.VERIFICATION_COMPLETED
    )
    assert kinds.index(EventType.VERIFICATION_COMPLETED) < kinds.index(EventType.DOWNLOAD_COMPLETED)
    started = next(e for e in events if e.type is EventType.VERIFICATION_STARTED)
    assert started.state is DownloadState.VERIFYING
    assert result_to_dict(result)["integrity"]["status"] == "verified"  # type: ignore[index]


def test_a_wrong_checksum_fails_the_download_and_sets_the_file_aside(tmp_path: Path) -> None:
    downloader, events = download(
        single_file_site("h264_aac.ts"),
        tmp_path / "a.ts",
        VerifyConfig(expected_checksum="f" * 64),
    )
    result = downloader.run()
    assert result.state is DownloadState.FAILED
    assert "Verification failed" in (result.error or "")
    assert result.integrity is not None
    assert result.integrity.status is VerificationStatus.FAILED
    assert result.integrity.invalid_path == str(tmp_path / "a.ts.invalid")
    assert not (tmp_path / "a.ts").exists()  # never left under its proper name
    assert (tmp_path / "a.ts.invalid").is_file()
    assert EventType.VERIFICATION_FAILED in [e.type for e in events]
    assert downloader.exception is not None
    assert downloader.exception.code == "VERIFICATION_FAILED"  # type: ignore[attr-defined]


def test_an_invalid_file_can_be_deleted_instead(tmp_path: Path) -> None:
    downloader, _ = download(
        single_file_site("h264_aac.ts"),
        tmp_path / "a.ts",
        VerifyConfig(expected_checksum="f" * 64, keep_invalid=False),
    )
    result = downloader.run()
    assert result.state is DownloadState.FAILED
    assert result.integrity is not None
    assert result.integrity.invalid_path is None
    assert list(tmp_path.iterdir()) == []


def test_a_matching_checksum_is_reported(tmp_path: Path) -> None:
    digest = hashlib.sha256(TS_FILE.read_bytes()).hexdigest()
    downloader, _ = download(
        single_file_site("h264_aac.ts", parts=3),
        tmp_path / "a.ts",
        VerifyConfig(expected_checksum=digest),
    )
    result = downloader.run()
    assert result.success, result.error
    assert result.integrity is not None
    assert result.integrity.checksum is not None
    assert result.integrity.checksum.matches is True


def test_strict_checking_stops_a_cut_off_segment(tmp_path: Path) -> None:
    site = single_file_site("h264_aac.ts")
    site.files["show/seg1.ts"] = site.files["show/seg1.ts"][:-50]  # cut in the middle of a packet
    lenient, _ = download(site, tmp_path / "lenient.ts", VerifyConfig(level="basic"))
    late = lenient.run()  # only noticed when the finished file is spot-checked
    assert late.state is DownloadState.FAILED
    assert "not a valid MPEG-TS file" in (late.error or "")
    strict, _ = download(site, tmp_path / "strict.ts", VerifyConfig(level="strong"))
    result = strict.run()
    assert result.state is DownloadState.FAILED
    assert "Segment 1" in (result.error or "")  # noticed at once, and which segment
    assert "middle of a packet" in (result.error or "")


@needs_ffmpeg
def test_strong_verification_catches_a_playlist_that_lies_about_the_length(tmp_path: Path) -> None:
    site = single_file_site("h264_aac.ts")
    site.files["show/index.m3u8"] = site.files["show/index.m3u8"].replace(
        b"#EXTINF:1.3", b"#EXTINF:60"
    )
    downloader, _ = download(site, tmp_path / "a.ts", VerifyConfig(level="strong"))
    result = downloader.run()
    assert result.state is DownloadState.FAILED
    assert result.integrity is not None
    assert "duration" in result.integrity.failures[0].name


@needs_ffmpeg
def test_matroska_and_audio_outputs_are_verified_too(tmp_path: Path) -> None:
    for fmt, name in ((OutputFormat.MKV, "a.mkv"), (OutputFormat.AUDIO, "a.m4a")):
        downloader, _ = download(
            single_file_site("h264_aac.ts"), tmp_path / name, VerifyConfig(level="strong"), fmt=fmt
        )
        result = downloader.run()
        assert result.success, result.error
        assert result.integrity is not None
        assert result.integrity.verified
        assert result.integrity.media is not None


def test_fragmented_mp4_streams_are_verified(tmp_path: Path) -> None:
    site = hls_site("fmp4", "show")
    config = DownloadConfig(
        network=NetworkConfig(retries=0, backoff_factor=0.001), verify=VerifyConfig(level="strong")
    )
    downloader = Downloader(
        BASE + "show/v0.m3u8",
        output=tmp_path / "v.mp4",
        config=config,
        transport=httpx.MockTransport(site),
    )
    result = downloader.run()
    assert result.success, result.error
    assert result.integrity is not None
    assert result.integrity.verified
