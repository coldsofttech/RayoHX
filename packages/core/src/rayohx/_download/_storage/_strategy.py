"""Choosing a storage strategy."""

from rayohx.enums import StorageStrategy
from rayohx.errors import ConfigurationError

#: How far past the segment being written the DIRECT and STREAMING strategies let workers run,
#: as a multiple of the number of workers.
WINDOW_FACTOR = 2


def choose_strategy(requested: StorageStrategy, *, sink_supports_resume: bool) -> StorageStrategy:
    """Resolve ``AUTO``: write to a resumable file directly, or stream if the sink cannot resume."""
    if requested is not StorageStrategy.AUTO:
        return requested
    return StorageStrategy.DIRECT if sink_supports_resume else StorageStrategy.STREAMING


def validate_strategy(strategy: StorageStrategy, *, sink_supports_resume: bool) -> None:
    """Reject a combination that cannot work.

    Raises:
        ConfigurationError: If the strategy needs a resumable file but the sink is a stream.
    """
    if strategy is StorageStrategy.DIRECT and not sink_supports_resume:
        raise ConfigurationError(
            "The DIRECT strategy writes a file, but this output is a stream.",
            hint="Use the STREAMING, BUFFERED, HYBRID or TEMPORARY strategy, or leave it on AUTO.",
        )
