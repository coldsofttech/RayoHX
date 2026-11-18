"""Looking inside a finished media file with ffprobe, when it is installed.

ffprobe is an optional program (it comes with FFmpeg). It is run as a separate process on a file
that is already on disk, and its answer is read as JSON. Nothing here changes any file.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rayohx._redaction import redact_text
from rayohx.errors import FinalizationError

logger = logging.getLogger(__name__)

PROBE_TIMEOUT = 120.0


@dataclass(frozen=True, slots=True, kw_only=True)
class StreamDetails:
    """One stream of a media file."""

    index: int
    #: ``video``, ``audio``, ``subtitle`` or ``other``.
    kind: str
    codec: str | None = None
    profile: str | None = None
    #: The codec's own level number (``40`` for H.264 level 4.0).
    level: int | None = None
    width: int | None = None
    height: int | None = None
    frame_rate: float | None = None
    bit_rate: int | None = None
    pixel_format: str | None = None
    channels: int | None = None
    channel_layout: str | None = None
    sample_rate: int | None = None
    language: str | None = None
    title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in _fields(self).items() if v is not None}


@dataclass(frozen=True, slots=True, kw_only=True)
class FileInfo:
    """What ffprobe found in a media file."""

    format_name: str | None = None
    duration: float | None = None
    size_bytes: int | None = None
    bit_rate: int | None = None
    streams: tuple[StreamDetails, ...] = ()
    tags: dict[str, str] = field(default_factory=dict)

    def of_kind(self, kind: str) -> list[StreamDetails]:
        return [s for s in self.streams if s.kind == kind]

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format_name,
            "duration": self.duration,
            "size_bytes": self.size_bytes,
            "bit_rate": self.bit_rate,
            "streams": [s.to_dict() for s in self.streams],
            "tags": dict(self.tags),
        }


def _fields(item: Any) -> dict[str, Any]:
    return {name: getattr(item, name) for name in item.__slots__}


def find_ffprobe(configured: Path | str | None = None) -> Path | None:
    """The ffprobe program: the configured one, else the first on the PATH."""
    if configured is not None:
        path = Path(configured)
        return path if path.is_file() else None
    found = shutil.which("ffprobe")
    return Path(found) if found else None


def _number(value: Any, kind: type = int) -> Any:
    try:
        return kind(float(value)) if kind is int else float(value)
    except (TypeError, ValueError):
        return None


def _rate(text: str | None) -> float | None:
    if not text or "/" not in text:
        result: float | None = _number(text, float)
        return result
    top, _, bottom = text.partition("/")
    try:
        return round(float(top) / float(bottom), 3) if float(bottom) else None
    except ValueError:
        return None


def _stream(raw: dict[str, Any]) -> StreamDetails:
    kind = {"video": "video", "audio": "audio", "subtitle": "subtitle"}.get(
        raw.get("codec_type", ""), "other"
    )
    tags = {str(k).lower(): str(v) for k, v in (raw.get("tags") or {}).items()}
    attached = (raw.get("disposition") or {}).get("attached_pic")
    return StreamDetails(
        index=int(raw.get("index", 0)),
        kind="other" if attached else kind,
        codec=raw.get("codec_name"),
        profile=raw.get("profile"),
        level=_number(raw.get("level")) if (_number(raw.get("level")) or 0) > 0 else None,
        width=_number(raw.get("width")),
        height=_number(raw.get("height")),
        frame_rate=_rate(raw.get("avg_frame_rate")) or _rate(raw.get("r_frame_rate")),
        bit_rate=_number(raw.get("bit_rate")),
        pixel_format=raw.get("pix_fmt"),
        channels=_number(raw.get("channels")),
        channel_layout=raw.get("channel_layout"),
        sample_rate=_number(raw.get("sample_rate")),
        language=tags.get("language") if tags.get("language") not in {None, "und"} else None,
        title=tags.get("title") or tags.get("handler_name"),
    )


def parse_probe(text: str) -> FileInfo:
    """Read ffprobe's JSON output."""
    data = json.loads(text)
    fmt = data.get("format") or {}
    return FileInfo(
        format_name=fmt.get("format_name"),
        duration=_number(fmt.get("duration"), float),
        size_bytes=_number(fmt.get("size")),
        bit_rate=_number(fmt.get("bit_rate")),
        streams=tuple(_stream(s) for s in data.get("streams") or []),
        tags={str(k).lower(): str(v) for k, v in (fmt.get("tags") or {}).items()},
    )


def probe_file(path: Path | str, ffprobe: Path | str | None = None) -> FileInfo:
    """Look inside a media file.

    Raises:
        FinalizationError: If ffprobe is not available, cannot read the file, or times out.
    """
    program = find_ffprobe(ffprobe)
    if program is None:
        raise FinalizationError(
            "ffprobe was not found.",
            hint="ffprobe comes with FFmpeg, an optional prerequisite: install it, or set "
            "its path.",
        )
    command = [
        str(program), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path),
    ]  # fmt: skip
    try:
        done = subprocess.run(  # noqa: S603 - fixed arguments, no shell
            command, capture_output=True, text=True, timeout=PROBE_TIMEOUT, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FinalizationError(f"ffprobe could not examine the file: {exc}") from exc
    if done.returncode != 0:
        detail = redact_text(
            (done.stderr or "").strip().splitlines()[-1:][0] if done.stderr else ""
        )
        raise FinalizationError(
            f"ffprobe cannot read the file{': ' + detail if detail else ''}.",
            hint="The file may be damaged or cut short.",
        )
    try:
        return parse_probe(done.stdout)
    except (ValueError, TypeError) as exc:
        raise FinalizationError("ffprobe gave an answer that could not be read.") from exc
