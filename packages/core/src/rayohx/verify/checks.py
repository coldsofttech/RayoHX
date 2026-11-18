"""Checking a finished output file."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rayohx._download._containers import validate_fmp4_file, validate_ts_file
from rayohx.enums import ContainerFormat, VerificationStatus, VerifyLevel
from rayohx.errors import CancellationError, FinalizationError
from rayohx.media.probe import FileInfo, find_ffprobe, probe_file
from rayohx.verify.checksum import file_checksum
from rayohx.verify.report import Check, CheckStatus, ChecksumResult, IntegrityReport

if TYPE_CHECKING:
    from rayohx.cancellation import CancellationToken
    from rayohx.config.verify import VerifyConfig

EBML_MAGIC = b"\x1a\x45\xdf\xa3"
#: How far the file's duration may be from the playlist's: the larger of this many seconds ...
DURATION_SLACK_SECONDS = 3.0
#: ... and this share of the expected duration.
DURATION_SLACK_RATIO = 0.05


@dataclass(frozen=True, slots=True, kw_only=True)
class Expectations:
    """What the playlist led us to expect of the finished file."""

    #: Total length in seconds, when the playlist is complete.
    duration: float | None = None
    video: bool = True
    audio: bool = False
    #: How many segments the output was built from.
    segments: int = 0


def _passed(name: str, detail: str = "") -> Check:
    return Check(name, CheckStatus.PASSED, detail)


def _failed(name: str, detail: str) -> Check:
    return Check(name, CheckStatus.FAILED, detail)


def _skipped(name: str, detail: str) -> Check:
    return Check(name, CheckStatus.SKIPPED, detail)


def check_present(path: Path, *, expected_segments: int = 0) -> Check:
    """The output exists and holds something."""
    if not path.exists():
        return _failed("output present", "The output file is missing.")
    if path.is_dir():
        count = sum(1 for item in path.iterdir() if item.is_file())
        if count == 0:
            return _failed("output present", "The output folder is empty.")
        if expected_segments and count < expected_segments:
            return _failed(
                "output present", f"Only {count} of {expected_segments} segment files are there."
            )
        return _passed("output present", f"{count} files")
    size = path.stat().st_size
    return (
        _failed("output present", "The output file is empty.")
        if size == 0
        else _passed("output present", f"{size} bytes")
    )


def check_container(path: Path, container: ContainerFormat) -> Check:
    """The file really is the kind of file its name says, as far as its structure shows."""
    if path.is_dir():
        return _skipped("container structure", "separate segment files")
    try:
        if container is ContainerFormat.MPEG_TS:
            validate_ts_file(path)
        elif container is ContainerFormat.FMP4:
            validate_fmp4_file(path)
        elif container is ContainerFormat.MATROSKA:
            with path.open("rb") as handle:
                if handle.read(4) != EBML_MAGIC:
                    return _failed("container structure", "It does not start like a Matroska file.")
        else:
            return _skipped("container structure", "no structure check for this kind of file")
    except FinalizationError as exc:
        return _failed("container structure", exc.message)
    return _passed("container structure", container.value)


def check_deep(
    path: Path, expected: Expectations, ffprobe: Path | str | None
) -> tuple[list[Check], FileInfo | None]:
    """Look inside the file with ffprobe: does it read, and hold the right streams and length?"""
    if find_ffprobe(ffprobe) is None:
        return [_skipped("deep inspection", "ffprobe is not installed")], None
    if path.is_dir():
        return [_skipped("deep inspection", "separate segment files")], None
    try:
        info = probe_file(path, ffprobe)
    except FinalizationError as exc:
        return [_failed("readable by ffprobe", exc.message)], None
    checks = [_passed("readable by ffprobe", info.format_name or "")]
    video, audio = info.of_kind("video"), info.of_kind("audio")
    if expected.video and not video:
        checks.append(_failed("streams", "The file has no video stream."))
    elif expected.audio and not audio:
        checks.append(_failed("streams", "The file has no audio stream."))
    else:
        checks.append(_passed("streams", f"{len(video)} video, {len(audio)} audio"))
    if expected.duration and expected.duration > 0:
        if info.duration is None:
            checks.append(_skipped("duration", "the file does not say how long it is"))
        else:
            slack = max(DURATION_SLACK_SECONDS, DURATION_SLACK_RATIO * expected.duration)
            if abs(info.duration - expected.duration) > slack:
                checks.append(
                    _failed(
                        "duration",
                        f"The file is {info.duration:.1f} s long but the playlist adds up to "
                        f"{expected.duration:.1f} s.",
                    )
                )
            else:
                checks.append(_passed("duration", f"{info.duration:.1f} s"))
    return checks, info


def verify_output(
    path: Path,
    *,
    container: ContainerFormat,
    config: VerifyConfig,
    expected: Expectations,
    cancel: CancellationToken | None = None,
) -> IntegrityReport:
    """Check a finished output as ``config`` asks and report what was found.

    Never raises for a problem with the file: a problem is a failed check. Cancelling raises
    ``CancellationError``.
    """
    started = time.monotonic()
    checks: list[Check] = []
    info: FileInfo | None = None
    checksum: ChecksumResult | None = None
    notes: list[str] = []
    if config.level is not VerifyLevel.NONE:
        checks.append(check_present(path, expected_segments=expected.segments))
        if checks[-1].status is CheckStatus.PASSED:
            checks.append(check_container(path, container))
    if config.level is VerifyLevel.STRONG and not any(
        c.status is CheckStatus.FAILED for c in checks
    ):
        deep, info = check_deep(path, expected, config.ffprobe_path)
        checks += deep
    if config.checksum is not None:
        if not path.is_file():
            checks.append(_skipped("checksum", "a folder of segments has no single checksum"))
        else:
            try:
                value = file_checksum(path, config.checksum, cancel)
            except CancellationError:
                raise
            except OSError as exc:
                checks.append(_failed("checksum", f"The file could not be read: {exc}"))
            else:
                checksum = ChecksumResult(config.checksum, value, config.expected_checksum)
                if checksum.matches is False:
                    checks.append(
                        _failed(
                            "checksum",
                            f"The {config.checksum} checksum is {value}, not the expected "
                            f"{config.expected_checksum}.",
                        )
                    )
                else:
                    checks.append(_passed("checksum", f"{config.checksum} {value}"))
    failed = any(c.status is CheckStatus.FAILED for c in checks)
    return IntegrityReport(
        status=VerificationStatus.FAILED if failed else VerificationStatus.VERIFIED,
        level=config.level,
        checks=tuple(checks),
        segments_checked=expected.segments,
        checksum=checksum,
        media=info,
        elapsed_seconds=time.monotonic() - started,
        notes=tuple(notes),
    )
