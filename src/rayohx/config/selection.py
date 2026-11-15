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


@dataclass(frozen=True, slots=True, kw_only=True)
class SelectionConfig:
    """Which tracks to download."""

    #: ``best``, ``worst``, ``auto`` or a height such as ``1080p`` (the nearest not above it).
    quality: str = "best"
    max_resolution: str | None = None
    #: Highest bandwidth in bits per second.
    max_bitrate: int | None = None
    #: Audio languages in order of preference. Empty means the stream's default track.
    audio_languages: tuple[str, ...] = ()
    #: Subtitle languages in order of preference. Empty means no subtitles.
    subtitle_languages: tuple[str, ...] = ()

    def __post_init__(self) -> None:
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

    def as_dict(self) -> dict[str, Any]:
        """A serializable view."""
        return {
            "quality": self.quality,
            "max_resolution": self.max_resolution,
            "max_bitrate": self.max_bitrate,
            "audio_languages": list(self.audio_languages),
            "subtitle_languages": list(self.subtitle_languages),
        }
