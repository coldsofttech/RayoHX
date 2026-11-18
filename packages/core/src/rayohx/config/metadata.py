"""Metadata settings: what is written into the output file besides the media."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rayohx.enums import MetadataPolicy
from rayohx.errors import ConfigurationError

if TYPE_CHECKING:
    from typing import Any

_MAX_TEXT = 2000


@dataclass(frozen=True, slots=True, kw_only=True)
class MetadataConfig:
    """What to write into the output file.

    Metadata can only be written by FFmpeg, so it goes into Matroska and audio files and into
    MP4 files made with FFmpeg (``remux_backend="ffmpeg"``). Other outputs get none, and the
    result says so.
    """

    policy: MetadataPolicy = MetadataPolicy.NONE
    #: Used with ``custom``, and with every other policy in place of what the stream says.
    title: str | None = None
    description: str | None = None
    language: str | None = None
    #: Whether ``preserve`` also fetches the cover image and writes the chapters.
    artwork: bool = True
    chapters: bool = True

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "policy", MetadataPolicy(str(self.policy).lower()))
        except ValueError:
            raise ConfigurationError(
                f"{self.policy!r} is not a metadata policy.",
                hint="Use one of: " + ", ".join(p.value for p in MetadataPolicy) + ".",
            ) from None
        for name in ("title", "description", "language"):
            value = getattr(self, name)
            if value is not None:
                text = value.strip()
                if len(text) > _MAX_TEXT or "\0" in text:
                    raise ConfigurationError(f"The metadata {name} is not valid.")
                object.__setattr__(self, name, text or None)

    @property
    def writes_anything(self) -> bool:
        return self.policy is not MetadataPolicy.NONE

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy.value,
            "title": self.title,
            "description": self.description,
            "language": self.language,
            "artwork": self.artwork,
            "chapters": self.chapters,
        }
