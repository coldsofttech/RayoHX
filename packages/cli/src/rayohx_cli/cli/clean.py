"""The ``clean`` command: remove working folders left behind by interrupted downloads."""

import shutil
import time
from pathlib import Path
from typing import Annotated

import typer
from rayohx.storage import find_workspaces, folder_size, is_workspace_in_use, last_used

from rayohx_cli import format as fmt
from rayohx_cli import output, params
from rayohx_cli.cli.common import confirm
from rayohx_cli.cli.root import app

DAY = 86400


def in_use(folder: Path) -> bool:
    """Whether a running download holds this folder's lock."""
    return is_workspace_in_use(folder)


@app.command()
def clean(
    folders: Annotated[
        list[Path] | None,
        typer.Argument(
            help="Folders to look in (default: the current folder). Use the folder you gave "
            "to --workspace or --output.",
            metavar="[FOLDER]...",
        ),
    ] = None,
    older_than: Annotated[
        float,
        typer.Option(
            "--older-than", min=0, help="Only folders not used for this many days (default 0)."
        ),
    ] = 0,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Only list what would be removed.")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask first.")] = False,
    json_output: params.JsonOutput = False,
) -> None:
    """Remove working folders left by interrupted downloads.

    Removing one means that download starts again from the beginning. Folders in use by a
    running download are never removed. The folders removed are printed on stdout.
    """
    now = time.time()
    candidates: list[tuple[Path, int, float]] = []
    skipped = 0
    for folder in folders or [Path.cwd()]:
        for workspace in find_workspaces(folder):
            if in_use(workspace):
                skipped += 1
                continue
            age = (now - last_used(workspace)) / DAY
            if age >= older_than:
                candidates.append((workspace, folder_size(workspace), age))
    if not candidates:
        if json_output:
            output.print_json({"removed": [], "bytes": 0})
        output.message("Nothing to clean." + (f" {skipped} in use." if skipped else ""))
        return
    total = sum(size for _, size, _ in candidates)
    for path, size, age in candidates:
        output.message(f"{path}  {fmt.size(size)}, last used {age:.1f} days ago")
    if dry_run:
        output.message(f"Would remove {len(candidates)} folder(s), {fmt.size(total)}.")
        return
    if not confirm(f"Remove {len(candidates)} folder(s) ({fmt.size(total)})?", yes=yes):
        raise typer.Exit(1)
    for path, _, _ in candidates:
        shutil.rmtree(path, ignore_errors=True)
        if not json_output:
            output.data(str(path))
    if json_output:
        output.print_json({"removed": [str(p) for p, _, _ in candidates], "bytes": total})
    output.message(f"Removed {len(candidates)} folder(s), {fmt.size(total)}.", style="green")
