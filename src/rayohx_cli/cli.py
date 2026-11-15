"""Command line interface built on Typer and Rich. It only parses input and shows output."""

from dataclasses import dataclass
from typing import Annotated

import typer

from rayohx import __version__
from rayohx_cli import output

app = typer.Typer(
    name="rayohx",
    help="Command line interface for [bold]RayoHX[/bold].",
    no_args_is_help=True,
    rich_markup_mode="rich",
    # run() reports errors briefly; Typer's own traceback would show local variables.
    pretty_exceptions_enable=False,
)


@dataclass
class State:
    """Global options shared with every command through the Typer context."""

    verbose: bool = False
    quiet: bool = False


def _show_version(value: bool) -> None:
    if value:
        output.console.print(f"rayohx {__version__}")
        raise typer.Exit


@app.callback()
def main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_show_version,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", envvar="RAYOHX_VERBOSE", help="Show extra detail."),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", envvar="RAYOHX_QUIET", help="Only show errors."),
    ] = False,
    no_color: Annotated[
        bool,
        typer.Option("--no-color", envvar="RAYOHX_NO_COLOR", help="Disable colored output."),
    ] = False,
) -> None:
    """Options that apply to every command."""
    if verbose and quiet:
        raise typer.BadParameter("--verbose and --quiet cannot be used together.")
    output.configure(no_color=no_color, verbose=verbose)
    ctx.obj = State(verbose=verbose, quiet=quiet)


def run() -> None:
    """Console script entry point: run the app and report unexpected errors briefly."""
    try:
        app()
    except Exception as exc:
        output.print_exception(exc)
        raise SystemExit(1) from exc
