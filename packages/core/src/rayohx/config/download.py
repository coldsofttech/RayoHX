"""Download settings: everything that shapes a download, grouped by area."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

    from rayohx.config.network import NetworkConfig
    from rayohx.config.output import OutputConfig
    from rayohx.config.selection import SelectionConfig
    from rayohx.config.storage import StorageConfig

DEFAULT_CONCURRENCY = 4
MAX_CONCURRENCY = 64


def _network() -> NetworkConfig:
    from rayohx.config.network import NetworkConfig

    return NetworkConfig()


def _storage() -> StorageConfig:
    from rayohx.config.storage import StorageConfig

    return StorageConfig()


def _output() -> OutputConfig:
    from rayohx.config.output import OutputConfig

    return OutputConfig()


def _selection() -> SelectionConfig:
    from rayohx.config.selection import SelectionConfig

    return SelectionConfig()


@dataclass(frozen=True, slots=True, kw_only=True)
class DownloadConfig:
    """Everything that shapes a download, grouped by area."""

    #: Segments fetched at the same time. Conservative by default.
    concurrency: int = DEFAULT_CONCURRENCY
    resume: bool = True
    network: NetworkConfig = field(default_factory=_network)
    storage: StorageConfig = field(default_factory=_storage)
    output: OutputConfig = field(default_factory=_output)
    selection: SelectionConfig = field(default_factory=_selection)

    def __post_init__(self) -> None:
        if not 1 <= self.concurrency <= MAX_CONCURRENCY:
            from rayohx.errors import ConfigurationError

            raise ConfigurationError(f"concurrency must be between 1 and {MAX_CONCURRENCY}.")

    def as_dict(self) -> dict[str, Any]:
        """A serializable view without secrets, safe for logs and resume state."""
        return {
            "concurrency": self.concurrency,
            "resume": self.resume,
            "network": self.network.as_dict(),
            "storage": self.storage.as_dict(),
            "output": self.output.as_dict(),
            "selection": self.selection.as_dict(),
        }
