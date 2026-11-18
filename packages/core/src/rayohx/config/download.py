"""Download settings: everything that shapes a download, grouped by area."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rayohx.config.metadata import MetadataConfig
from rayohx.config.network import NetworkConfig
from rayohx.config.output import OutputConfig
from rayohx.config.selection import SelectionConfig
from rayohx.config.storage import StorageConfig
from rayohx.config.verify import VerifyConfig
from rayohx.errors import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

DEFAULT_CONCURRENCY = 4
MAX_CONCURRENCY = 64


@dataclass(frozen=True, slots=True, kw_only=True)
class DownloadConfig:
    """Everything that shapes a download, grouped by area."""

    #: Segments fetched at the same time. Conservative by default.
    concurrency: int = DEFAULT_CONCURRENCY
    resume: bool = True
    network: NetworkConfig = field(default_factory=NetworkConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    selection: SelectionConfig = field(default_factory=SelectionConfig)
    verify: VerifyConfig = field(default_factory=VerifyConfig)
    metadata: MetadataConfig = field(default_factory=MetadataConfig)
    #: Your own way to get an AES-128 key. Called with the key's address from the playlist
    #: (any scheme) and returns the 16 key bytes. Use it when the key comes from somewhere the
    #: HTTP layer cannot reach. It replaces every other way of fetching keys. It is a hook for
    #: plain AES-128 only: protected (DRM) streams are still refused.
    key_fetcher: Callable[[str], bytes] | None = field(default=None, repr=False)
    #: Allow ``file:`` key addresses, which read a local file. Off by default, because a stream
    #: from the internet could otherwise make RayoHX read files from this machine.
    allow_file_keys: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.concurrency <= MAX_CONCURRENCY:
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
            "verify": self.verify.as_dict(),
            "metadata": self.metadata.as_dict(),
            "key_fetcher": self.key_fetcher is not None,
            "allow_file_keys": self.allow_file_keys,
        }
