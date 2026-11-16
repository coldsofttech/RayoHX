"""Storage settings: where working data lives and how much of it may pile up."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rayohx.config._common import check_positive
from rayohx.enums import StorageStrategy
from rayohx.errors import ConfigurationError

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

DEFAULT_BUFFER_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True, kw_only=True)
class StorageConfig:
    """Where working data lives and how much of it may pile up."""

    strategy: StorageStrategy = StorageStrategy.AUTO
    #: Folder for working files. ``None`` lets the engine pick a folder beside the output.
    workspace_dir: Path | None = None
    #: Memory the bounded buffer may hold.
    buffer_bytes: int = DEFAULT_BUFFER_BYTES
    #: Most temporary data allowed on disk at once; ``None`` means no explicit limit.
    max_temp_bytes: int | None = None
    #: Free space that must remain after the download.
    reserve_bytes: int = 256 * 1024 * 1024
    #: Keep resume state after a failure or cancellation.
    keep_state_on_failure: bool = True
    #: Check that the disk has room before and during the download. Turn it off only when the
    #: free-space figure is wrong, for example on some network drives.
    check_space: bool = True

    def __post_init__(self) -> None:
        check_positive("buffer_bytes", self.buffer_bytes)
        check_positive("max_temp_bytes", self.max_temp_bytes, allow_none=True)
        if self.reserve_bytes < 0:
            raise ConfigurationError("reserve_bytes must not be negative.")

    def as_dict(self) -> dict[str, Any]:
        """A serializable view."""
        return {
            "strategy": self.strategy.value,
            "workspace_dir": str(self.workspace_dir) if self.workspace_dir else None,
            "buffer_bytes": self.buffer_bytes,
            "max_temp_bytes": self.max_temp_bytes,
            "reserve_bytes": self.reserve_bytes,
            "keep_state_on_failure": self.keep_state_on_failure,
            "check_space": self.check_space,
        }
