"""Output settings: what file is produced and how it is checked."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rayohx.enums import OutputFormat, RemuxBackend

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputConfig:
    """What file is produced and how it is checked."""

    path: Path | None = None
    format: OutputFormat = OutputFormat.AUTO
    #: Replace an existing file. Off by default so a download never destroys data silently.
    overwrite: bool = False
    validate: bool = True
    remux_backend: RemuxBackend = RemuxBackend.AUTO
    #: Path of an FFmpeg program to use when the backend is ``FFMPEG`` or ``AUTO`` needs it.
    ffmpeg_path: Path | None = None

    def __post_init__(self) -> None:
        if self.path is not None:
            text = str(self.path)
            if not text.strip() or text == ".":
                from rayohx.errors import ConfigurationError

                raise ConfigurationError("The output path must not be empty.")
            if "\0" in text:
                from rayohx.errors import ConfigurationError

                raise ConfigurationError("The output path contains a null character.")

    def as_dict(self) -> dict[str, Any]:
        """A serializable view."""
        return {
            "path": str(self.path) if self.path else None,
            "format": self.format.value,
            "overwrite": self.overwrite,
            "validate": self.validate,
            "remux_backend": self.remux_backend.value,
            "ffmpeg_path": str(self.ffmpeg_path) if self.ffmpeg_path else None,
        }
