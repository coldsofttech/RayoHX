"""Download engine options."""

from pathlib import Path
from typing import Annotated

import typer
from rayohx import StorageStrategy

from rayohx_cli.params.panels import ENGINE

Concurrency = Annotated[
    int | None,
    typer.Option(
        "--concurrency",
        "-j",
        envvar="RAYOHX_CONCURRENCY",
        min=1,
        max=64,
        help="Segments to download at the same time (default 4).",
        rich_help_panel=ENGINE,
    ),
]
Resume = Annotated[
    bool,
    typer.Option(
        "--resume/--no-resume",
        envvar="RAYOHX_RESUME",
        help="Continue an interrupted download where it stopped.",
        rich_help_panel=ENGINE,
    ),
]
Storage = Annotated[
    StorageStrategy,
    typer.Option(
        "--storage",
        envvar="RAYOHX_STORAGE",
        case_sensitive=False,
        help="Where finished segments wait: auto, direct, streaming, buffered, temporary, hybrid.",
        rich_help_panel=ENGINE,
    ),
]
Workspace = Annotated[
    Path | None,
    typer.Option(
        "--workspace",
        envvar="RAYOHX_WORKSPACE",
        help="A folder for working files (default: beside the output).",
        rich_help_panel=ENGINE,
    ),
]
BufferSize = Annotated[
    str | None,
    typer.Option(
        "--buffer-size",
        envvar="RAYOHX_BUFFER_SIZE",
        help="Memory for the segment buffer, for example 64M.",
        rich_help_panel=ENGINE,
    ),
]
MaxTempSize = Annotated[
    str | None,
    typer.Option(
        "--max-temp-size",
        envvar="RAYOHX_MAX_TEMP_SIZE",
        help="Most working disk space to use, for example 2G.",
        rich_help_panel=ENGINE,
    ),
]
