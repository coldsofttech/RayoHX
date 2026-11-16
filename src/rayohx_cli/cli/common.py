"""What every command shares: exit codes and turning bad settings into a usage error."""

from typing import NoReturn

import typer

from rayohx.config import DownloadConfig
from rayohx.errors import ConfigurationError, RayoHXError
from rayohx_cli import output
from rayohx_cli.values import build_config

EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_CANCELLED = 130


def usage_error(exc: RayoHXError) -> NoReturn:
    output.error_from(exc)
    raise typer.Exit(EXIT_USAGE)


def make_config(**options: object) -> DownloadConfig:
    """Build the engine's settings, turning a bad value into a usage error."""
    try:
        return build_config(**options)  # type: ignore[arg-type]
    except ConfigurationError as exc:
        usage_error(exc)
