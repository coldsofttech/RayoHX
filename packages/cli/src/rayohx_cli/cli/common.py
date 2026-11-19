"""What every command shares: exit codes and turning bad settings into a usage error."""

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import typer
from rayohx.config import DownloadConfig
from rayohx.enums import ErrorCategory
from rayohx.errors import ConfigurationError, RayoHXError
from rayohx.platform.diagnostics import category_of
from rayohx.redaction import redact_url

from rayohx_cli import output
from rayohx_cli.values import build_config

EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_VERIFICATION = 3
EXIT_AUTH = 4
EXIT_STORAGE = 5
EXIT_AUTOMATION = 6
EXIT_PARTIAL = 7
EXIT_CANCELLED = 130

_BY_CATEGORY = {
    ErrorCategory.VERIFICATION: EXIT_VERIFICATION,
    ErrorCategory.AUTHENTICATION: EXIT_AUTH,
    ErrorCategory.STORAGE: EXIT_STORAGE,
    ErrorCategory.AUTOMATION: EXIT_AUTOMATION,
}


_STATE = {"non_interactive": False}


def set_non_interactive(value: bool) -> None:
    _STATE["non_interactive"] = value


def non_interactive() -> bool:
    """Whether commands must never wait for an answer (``--non-interactive``, for scripts)."""
    return _STATE["non_interactive"]


def confirm(question: str, *, yes: bool) -> bool:
    """Ask a yes/no question, unless ``yes`` was given. Never waits when non-interactive."""
    if yes:
        return True
    if non_interactive():
        usage_error(
            ConfigurationError(
                f"{question} needs your confirmation, and this run is non-interactive.",
                hint="Add --yes to go ahead.",
            )
        )
    return typer.confirm(question, err=True)


def legacy_exit_codes() -> bool:
    """Whether ``RAYOHX_EXIT_CODES=legacy`` asks for the old codes (every failure is 1)."""
    return os.environ.get("RAYOHX_EXIT_CODES", "").strip().lower() == "legacy"


def exit_for_category(category: ErrorCategory | None) -> int:
    """The exit code for a failure of this kind."""
    if legacy_exit_codes() or category is None:
        return EXIT_FAILED
    return _BY_CATEGORY.get(category, EXIT_FAILED)


def exit_for_error(exc: BaseException | None) -> int:
    """The exit code for an error: its category decides, never its message."""
    return exit_for_category(exc.category if isinstance(exc, RayoHXError) else None)


def exit_for_code(code: str | None) -> int:
    """The exit code for a stable error code such as ``HTTP_403`` or ``STORAGE_LOW``."""
    return exit_for_category(category_of(code) if code else None)


def exit_for_batch(failures: Sequence[int], succeeded: int) -> int:
    """One code for several operations: 7 if only some failed, else the shared code (0 if none)."""
    if not failures:
        return 0
    if legacy_exit_codes():
        return EXIT_FAILED
    if succeeded:
        return EXIT_PARTIAL
    return failures[0] if len(set(failures)) == 1 else EXIT_FAILED


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


@dataclass(frozen=True)
class Source:
    """Where a playlist comes from: a web address, or a local file read into ``text``."""

    url: str
    text: str | None = None

    @property
    def label(self) -> str:
        return redact_url(self.url) if self.text is None else self.url


PLACEHOLDER_HOST = "https://playlist.invalid/"


def open_source(target: str, base_url: str | None) -> Source:
    """A web address as it is, or a local playlist file read in.

    A local file's relative addresses are resolved against ``base_url``. Without one, a
    placeholder address is used, which suits playlists whose addresses are all absolute.
    """
    if target.lower().startswith(("http://", "https://")):
        return Source(target)
    path = Path(target).expanduser()
    if not path.is_file():
        return Source(target)  # not a file: let the address check explain what is wrong
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        usage_error(ConfigurationError(f"The playlist file {path} cannot be read."))
    return Source(base_url or PLACEHOLDER_HOST + path.name, text)
