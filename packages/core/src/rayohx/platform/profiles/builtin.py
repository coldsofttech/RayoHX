"""The profiles every installation has. They cannot be changed; duplicate one to adapt it."""

from __future__ import annotations

from rayohx.config.selection import ALL_TRACKS
from rayohx.platform.jobs.retry import RetryPolicy
from rayohx.platform.profiles.model import DownloadProfile

BEST_QUALITY = DownloadProfile(
    id="best-quality",
    name="Best Quality",
    description="The highest quality the stream offers, in the container it comes in.",
    options={"selection": {"quality": "best"}},
    builtin=True,
)
FULL_HD = DownloadProfile(
    id="1080p",
    name="1080p",
    description="The best quality up to 1080p.",
    options={"selection": {"quality": "best", "max_resolution": "1080p"}},
    builtin=True,
)
MOBILE = DownloadProfile(
    id="mobile",
    name="Mobile",
    description="Small files for phones and tablets: up to 480p, MP4, little working space.",
    options={
        "selection": {"quality": "best", "max_resolution": "480p", "max_bitrate": 1_500_000},
        "output": {"format": "mp4"},
        "storage": {"strategy": "streaming"},
    },
    verify="basic",
    builtin=True,
)
ARCHIVE = DownloadProfile(
    id="archive",
    name="Archive",
    description=(
        "Keep everything: the best quality, every audio and subtitle track, in Matroska, with "
        "metadata kept and strong verification. Needs FFmpeg for the Matroska file."
    ),
    options={
        "selection": {
            "quality": "best",
            "audio_languages": [ALL_TRACKS],
            "subtitle_languages": [ALL_TRACKS],
        },
        "output": {"format": "mkv"},
        "storage": {"keep_state_on_failure": True},
    },
    retry=RetryPolicy(max_attempts=5, initial_delay=30),
    metadata="preserve",
    verify="strong",
    builtin=True,
)
CUSTOM = DownloadProfile(
    id="custom",
    name="Custom",
    description="The engine's own defaults. Duplicate it to make a profile of your own.",
    options={},
    builtin=True,
)

BUILTIN_PROFILES: tuple[DownloadProfile, ...] = (BEST_QUALITY, FULL_HD, MOBILE, ARCHIVE, CUSTOM)
