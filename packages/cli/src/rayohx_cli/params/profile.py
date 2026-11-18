"""The ``--profile`` option."""

from typing import Annotated

import typer

from rayohx_cli.params.panels import ENGINE

ProfileOption = Annotated[
    str | None,
    typer.Option(
        "--profile",
        envvar="RAYOHX_PROFILE",
        help=(
            "Use a saved profile (see [bold]rayohx profile list[/bold]). Options you give on "
            "the command line win over the profile; the profile wins over the settings file."
        ),
        rich_help_panel=ENGINE,
    ),
]
