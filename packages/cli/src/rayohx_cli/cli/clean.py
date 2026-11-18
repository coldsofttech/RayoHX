"""The ``clean`` command: remove working folders left behind by interrupted downloads."""

import re
import shutil
import time
from pathlib import Path
from typing import Annotated

import typer
from rayohx._download._workspace import FOLDER_PREFIX, LOCK_FILE, STATE_FILE, _FileLock

from rayohx_cli import format as fmt
from rayohx_cli import output
from rayohx_cli.cli.root import app

_KEY_FOLDER = re.compile(r"^[0-9a-f]{16}$")
DAY = 86400


def find_workspaces(folder: Path) -> list[Path]:
    """Working folders directly inside ``folder``: ``.rayohx-*`` ones, and the hash-named ones
    inside a ``--workspace`` folder (they hold a resume state file)."""
    found = []
    try:
        children = sorted(folder.iterdir())
    except OSError:
        return []
    for child in children:
        if child.is_symlink() or not child.is_dir():
            continue
        named = child.name.startswith(FOLDER_PREFIX)
        keyed = bool(_KEY_FOLDER.match(child.name)) and (child / STATE_FILE).is_file()
        if named or keyed:
            found.append(child)
    return found


def folder_size(folder: Path) -> int:
    return sum(item.stat().st_size for item in folder.rglob("*") if item.is_file())


def last_used(folder: Path) -> float:
    state = folder / STATE_FILE
    return (state if state.is_file() else folder).stat().st_mtime


def in_use(folder: Path) -> bool:
    """Whether a running download holds this folder's lock."""
    lock = folder / LOCK_FILE
    if not lock.is_file():
        return False
    probe = _FileLock(lock)
    if probe.acquire():
        probe.release()
        return False
    return True


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
        output.message("Nothing to clean." + (f" {skipped} in use." if skipped else ""))
        return
    total = sum(size for _, size, _ in candidates)
    for path, size, age in candidates:
        output.message(f"{path}  {fmt.size(size)}, last used {age:.1f} days ago")
    if dry_run:
        output.message(f"Would remove {len(candidates)} folder(s), {fmt.size(total)}.")
        return
    if not yes and not typer.confirm(
        f"Remove {len(candidates)} folder(s) ({fmt.size(total)})?", err=True
    ):
        raise typer.Exit(1)
    for path, _, _ in candidates:
        shutil.rmtree(path, ignore_errors=True)
        output.data(str(path))
    output.message(f"Removed {len(candidates)} folder(s), {fmt.size(total)}.", style="green")
