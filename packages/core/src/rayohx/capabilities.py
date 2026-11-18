"""What this machine can do beyond the built-in engine, so settings can be checked early.

The engine copies and re-wraps streams on its own. A few outputs need FFmpeg, an optional program
that is found on the PATH or at a path you give. Asking before a download starts means a setting
that cannot work is refused at once, not after hours of downloading.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from rayohx._mux.ffmpeg import find_ffmpeg
from rayohx.enums import OutputFormat

__all__ = ["Capabilities", "detect", "find_ffmpeg", "output_requirements"]

#: The programs each output format needs, besides the engine itself.
_REQUIRES_FFMPEG = frozenset({OutputFormat.MKV, OutputFormat.AUDIO})


@dataclass(frozen=True, slots=True)
class Capabilities:
    """The optional programs found."""

    ffmpeg: Path | None = None
    ffprobe: Path | None = None

    def supports(self, output: OutputFormat) -> bool:
        """Whether files of this format can be made here."""
        return output not in _REQUIRES_FFMPEG or self.ffmpeg is not None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "ffmpeg": str(self.ffmpeg) if self.ffmpeg else None,
            "ffprobe": str(self.ffprobe) if self.ffprobe else None,
        }


def detect(ffmpeg_path: Path | str | None = None) -> Capabilities:
    """Look for FFmpeg (at ``ffmpeg_path``, else on the PATH) and ffprobe."""
    ffmpeg = find_ffmpeg(ffmpeg_path)
    found = shutil.which("ffprobe")
    probe = None
    if ffmpeg is not None:
        sibling = ffmpeg.with_name(ffmpeg.name.replace("ffmpeg", "ffprobe"))
        probe = sibling if sibling.is_file() and sibling != ffmpeg else None
    if probe is None and found:
        probe = Path(found)
    return Capabilities(ffmpeg=ffmpeg, ffprobe=probe)


def output_requirements(output: OutputFormat) -> tuple[str, ...]:
    """The optional programs a format needs: ``("ffmpeg",)`` or nothing."""
    return ("ffmpeg",) if output in _REQUIRES_FFMPEG else ()
