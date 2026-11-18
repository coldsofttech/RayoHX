"""Using an FFmpeg program that is already installed, when the built-in remuxer cannot cope.

Rayo never ships or links FFmpeg: it is an optional prerequisite, found on the PATH or at a path the
user gives, and run as a separate program on files already downloaded. It is only ever asked to
*copy* streams (``-c copy``) into an MP4, a Matroska file or an audio file. It does not transcode.
"""

import logging
import shutil
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from rayohx._mux.fmp4 import language_code
from rayohx._redaction import redact_text
from rayohx.cancellation import CancellationToken
from rayohx.errors import CancellationError, FinalizationError

logger = logging.getLogger(__name__)

FRAGMENTED = "frag_keyframe+empty_moov+delay_moov+default_base_moof"
POLL = 0.2


@dataclass(frozen=True, slots=True)
class FfmpegInput:
    """A downloaded file to be copied into the output.

    ``audio_codecs`` names the codecs of the file's audio streams in order (``"aac"`` means AAC in
    ADTS framing, which needs a header fix to go into an MP4). ``language`` is put on the file's
    audio streams.
    """

    path: Path
    audio_codecs: tuple[str, ...] = ()
    language: str | None = None


def find_ffmpeg(configured: Path | str | None = None) -> Path | None:
    """The FFmpeg program to use: the configured one, else the first on the PATH."""
    if configured is not None:
        path = Path(configured)
        return path if path.is_file() else None
    found = shutil.which("ffmpeg")
    return Path(found) if found else None


#: The muxer FFmpeg is told to use for each audio file extension.
AUDIO_MUXERS = {
    ".m4a": "mp4",
    ".aac": "adts",
    ".mp3": "mp3",
    ".ac3": "ac3",
    ".eac3": "eac3",
    ".mka": "matroska",
}


def build_command(
    executable: Path,
    inputs: Sequence[FfmpegInput],
    output: Path,
    *,
    kind: str = "mp4",
    audio_only: bool = False,
) -> list[str]:
    """The command that copies the streams of ``inputs`` into one file.

    ``kind`` is ``mp4`` (the default), ``mkv``, or ``audio``, where the container follows the
    extension of ``output`` and only sound is kept. Streams are only ever copied. The one change
    made is rewriting the headers of AAC from a transport stream, which does not alter the sound.
    """
    command = [str(executable), "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
    for item in inputs:
        command += ["-i", str(item.path)]
    for index in range(len(inputs)):
        if not audio_only:
            command += ["-map", f"{index}:v?"]
        command += ["-map", f"{index}:a?"]
    command += ["-c", "copy", "-sn", "-dn"]
    if audio_only:
        command += ["-vn"]
    muxer = AUDIO_MUXERS.get(output.suffix.lower(), "matroska") if audio_only else None
    fix_aac = not audio_only or muxer in {"mp4", "matroska"}
    audio = 0
    for item in inputs:
        codecs = item.audio_codecs or (("",) if item.language else ())
        for codec in codecs:
            if codec == "aac" and fix_aac:
                command += [f"-bsf:a:{audio}", "aac_adtstoasc"]
            if item.language and muxer not in {"adts", "mp3", "ac3", "eac3"}:
                command += [f"-metadata:s:a:{audio}", f"language={language_code(item.language)}"]
            audio += 1
    if audio_only:
        if muxer == "mp4":
            command += ["-movflags", "+faststart"]
        command += ["-f", muxer or "matroska"]
    elif kind == "mkv":
        command += ["-f", "matroska"]
    else:
        command += ["-movflags", FRAGMENTED, "-f", "mp4"]
    command.append(str(output))
    return command


def remux(
    executable: Path,
    inputs: Sequence[FfmpegInput],
    output: Path,
    *,
    cancel: CancellationToken | None = None,
    kind: str = "mp4",
    audio_only: bool = False,
) -> None:
    """Run FFmpeg to copy ``inputs`` into ``output`` (see ``build_command``).

    Raises:
        FinalizationError: If FFmpeg fails or cannot be started.
        CancellationError: If ``cancel`` fires; FFmpeg is stopped.
    """
    command = build_command(executable, inputs, output, kind=kind, audio_only=audio_only)
    try:
        process = subprocess.Popen(  # noqa: S603 - fixed arguments, no shell
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        raise FinalizationError(
            f"FFmpeg could not be started: {exc.strerror or exc}",
            hint="Check the FFmpeg path.",
        ) from exc
    while True:
        try:
            _, error = process.communicate(timeout=POLL)
            break
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_cancelled:
                process.kill()
                process.communicate()
                raise CancellationError("The download was cancelled.") from None
            time.sleep(0)
    if process.returncode != 0:
        detail = redact_text((error or "").strip().splitlines()[-1] if error else "no details")
        raise FinalizationError(
            f"FFmpeg could not join the stream: {detail}",
            hint="The downloaded data may be damaged or in an unusual format.",
        )
