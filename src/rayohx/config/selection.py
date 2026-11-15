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
    #: Audio languages to download, one track each, in order of preference. If none is available
    #: the stream's default track is used. Empty means the default track.
    audio_languages: tuple[str, ...] = ()
    #: Subtitle languages to download, one track each. Empty means no subtitles.
    subtitle_languages: tuple[str, ...] = ()
    #: Exact track names to download (as shown by ``inspect``), matched ignoring case.
    audio_names: tuple[str, ...] = ()
    subtitle_names: tuple[str, ...] = ()

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
        }
