"""Selection settings: which tracks to download."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rayohx.config._common import check_positive
from rayohx.errors import ConfigurationError

if TYPE_CHECKING:
    from typing import Any

_QUALITY = re.compile(r"^(best|worst|auto|\d{3,4}p)$", re.IGNORECASE)
_LANGUAGE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
_RESOLUTION = re.compile(r"^\d{3,4}p$", re.IGNORECASE)
_EXACT_SIZE = re.compile(r"^(\d{2,5})x(\d{2,5})$", re.IGNORECASE)


@dataclass(frozen=True, slots=True, kw_only=True)
class SelectionConfig:
    """Which tracks to download."""

    #: ``best``, ``worst``, ``auto`` or a height such as ``1080p`` (the nearest not above it).
    quality: str = "best"
    max_resolution: str | None = None
    #: Highest bandwidth in bits per second.
    max_bitrate: int | None = None
    #: Audio languages to download, one track each, in order of preference. If none is available
    #: the stream's default track is used. Empty means the default track.
    audio_languages: tuple[str, ...] = ()
    #: Subtitle languages to download, one track each. Empty means no subtitles.
    subtitle_languages: tuple[str, ...] = ()
    #: Exact track names to download (as shown by ``inspect``), matched ignoring case.
    audio_names: tuple[str, ...] = ()
    subtitle_names: tuple[str, ...] = ()
    #: Download only the video stream, leaving out separate audio and subtitle tracks.
    video_only: bool = False
    #: The stream to download, by its number in the listing (the first is 1). Chooses that stream
    #: itself, so it cannot be combined with the other ways of choosing one.
    variant: int | None = None
    #: Only streams with exactly this picture size, such as ``1280x720``.
    resolution: str | None = None
    #: Only streams with exactly this bandwidth or average bandwidth, in bits per second.
    bandwidth: int | None = None
    #: Only streams with exactly this name (the ``NAME`` of the playlist), ignoring case.
    variant_name: str | None = None

    def __post_init__(self) -> None:
        check_positive("variant", self.variant, allow_none=True)
        check_positive("bandwidth", self.bandwidth, allow_none=True)
        if self.resolution is not None:
            match = _EXACT_SIZE.match(self.resolution.strip())
            if not match:
                raise ConfigurationError(
                    f"resolution {self.resolution!r} is not valid.",
                    hint="Use the width and height, such as 1280x720.",
                )
            object.__setattr__(self, "resolution", f"{int(match[1])}x{int(match[2])}")
        if self.variant_name is not None and not self.variant_name.strip():
            raise ConfigurationError("variant_name must not be empty.")
        if self.variant is not None and any(
            value is not None
            for value in (
                self.resolution,
                self.bandwidth,
                self.variant_name,
                self.max_resolution,
                self.max_bitrate,
            )
        ):
            raise ConfigurationError(
                "variant chooses a stream by itself, so it cannot be combined with "
                "resolution, bandwidth, variant_name, max_resolution or max_bitrate."
            )
        if not _QUALITY.match(self.quality):
            raise ConfigurationError(
                f"quality {self.quality!r} is not valid.",
                hint="Use best, worst, auto, or a height such as 1080p.",
            )
        object.__setattr__(self, "quality", self.quality.lower())
        if self.max_resolution is not None:
            if not _RESOLUTION.match(self.max_resolution):
                raise ConfigurationError(
                    f"max_resolution {self.max_resolution!r} is not valid.",
                    hint="Use a height such as 1080p.",
                )
            object.__setattr__(self, "max_resolution", self.max_resolution.lower())
        check_positive("max_bitrate", self.max_bitrate, allow_none=True)
        for name in ("audio_languages", "subtitle_languages"):
            values = tuple(getattr(self, name))
            for language in values:
                if not _LANGUAGE.match(language):
                    raise ConfigurationError(f"{language!r} is not a valid language code.")
            object.__setattr__(self, name, values)
        for name in ("audio_names", "subtitle_names"):
            names = tuple(getattr(self, name))
            if any(not item.strip() for item in names):
                raise ConfigurationError("Track names must not be empty.")
            object.__setattr__(self, name, names)

    def as_dict(self) -> dict[str, Any]:
        """A serializable view."""
        return {
            "quality": self.quality,
            "max_resolution": self.max_resolution,
            "max_bitrate": self.max_bitrate,
            "audio_languages": list(self.audio_languages),
            "subtitle_languages": list(self.subtitle_languages),
            "audio_names": list(self.audio_names),
            "subtitle_names": list(self.subtitle_names),
            "video_only": self.video_only,
            "variant": self.variant,
            "resolution": self.resolution,
            "bandwidth": self.bandwidth,
            "variant_name": self.variant_name,
        }
