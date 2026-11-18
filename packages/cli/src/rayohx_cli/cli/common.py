"""What every command shares: exit codes and turning bad settings into a usage error."""

import sys
from collections.abc import Sequence
from pathlib import Path
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


def gather_urls(urls: Sequence[str], input_file: Path | None) -> list[str]:
    """The addresses given as arguments, then those listed in ``input_file`` (``-`` is stdin)."""
    found = list(urls)
    if input_file is not None:
        try:
            if str(input_file) == "-":
                text = sys.stdin.read()
            else:
                text = input_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            usage_error(ConfigurationError(f"The address list {input_file} cannot be read."))
            raise exc  # unreachable: usage_error exits
        found.extend(
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    if not found:
        usage_error(
            ConfigurationError(
                "There is nothing to download.",
                hint="Give an address, or a list of addresses with --input-file.",
            )
        )
    return found
