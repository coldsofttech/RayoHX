"""Display options."""

from typing import Annotated

import typer

from rayohx_cli.params.panels import DISPLAY

JsonOutput = Annotated[
    bool,
    typer.Option(
        "--json",
        help="Print the result as JSON on stdout, for other programs.",
        rich_help_panel=DISPLAY,
    ),
]
ProgressMode = Annotated[
    str,
    typer.Option(
        "--progress",
        envvar="RAYOHX_PROGRESS",
        help="How to show progress: auto (a bar on a terminal, lines otherwise), bar, plain, none.",
        rich_help_panel=DISPLAY,
    ),
]
