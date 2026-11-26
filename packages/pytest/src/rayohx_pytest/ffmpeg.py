"""FFmpeg as a test oracle: compare output with what an independent decoder reports.

FFmpeg and ffprobe are only a reference to compare against. Tests marked ``needs_ffmpeg`` are
skipped when they are not installed.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HAS_FFPROBE = shutil.which("ffprobe") is not None and shutil.which("ffmpeg") is not None
needs_ffmpeg = pytest.mark.skipif(
    not HAS_FFPROBE,
    reason="ffmpeg and ffprobe are used only as a test oracle and are not installed",
)


def probe(path: Path) -> dict[str, list[dict[str, str]]]:
    """Streams of a file as reported by ``ffprobe``, grouped by type."""
    result = subprocess.run(  # noqa: S603
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    streams: dict[str, list[dict[str, str]]] = {"video": [], "audio": []}
    for stream in json.loads(result.stdout)["streams"]:
        streams.setdefault(stream["codec_type"], []).append(stream)
    return streams


def decodes_cleanly(path: Path) -> bool:
    """Whether ``ffmpeg`` can decode every frame of the file without errors."""
    result = subprocess.run(  # noqa: S603
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and not result.stderr.strip()


def decoded(path: Path, kind: str) -> tuple[int, str]:
    """Decoded frame count and hash (video), or the hash of the decoded samples (audio)."""
    if kind == "video":
        result = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(path),
                "-map",
                "0:v",
                "-f",
                "framemd5",
                "-",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        lines = [
            line.split(",")[-1].strip()
            for line in result.stdout.splitlines()
            if not line.startswith("#")
        ]
        return len(lines), "".join(lines)
    result = subprocess.run(  # noqa: S603
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a", "-f", "md5", "-"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    return 0, result.stdout.strip()
