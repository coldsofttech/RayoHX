"""Find and remove the working folders that interrupted downloads leave behind.

A working folder holds what a resume needs. Removing one means that download starts again from the
beginning. A folder a running download holds the lock of is reported as ``in_use`` and never
removed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from rayohx.models.download.workspace import LeftoverWorkspace

__all__ = ["find_workspaces", "remove_workspaces"]

_SECONDS_PER_DAY = 86400


def find_workspaces(
    folders: Iterable[Path] | None = None, older_than_days: float = 0
) -> list[LeftoverWorkspace]:
    """Working folders directly inside each of ``folders`` (default: the current folder).

    Finds ``.rayohx-*`` folders, and the hash-named ones inside a ``workspace`` folder (they hold a
    resume state file). Only folders not used for at least ``older_than_days`` are returned.
    """
    import re
    import time
    from pathlib import Path

    from rayohx._download._workspace import FOLDER_PREFIX, LOCK_FILE, STATE_FILE, _FileLock
    from rayohx.models.download.workspace import LeftoverWorkspace

    hashed = re.compile(r"^[0-9a-f]{16}$")
    now = time.time()
    found: list[LeftoverWorkspace] = []
    for folder in folders or [Path.cwd()]:
        try:
            children = sorted(Path(folder).iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_symlink() or not child.is_dir():
                continue
            named = child.name.startswith(FOLDER_PREFIX)
            keyed = bool(hashed.match(child.name)) and (child / STATE_FILE).is_file()
            if not (named or keyed):
                continue
            state = child / STATE_FILE
            age = (now - (state if state.is_file() else child).stat().st_mtime) / _SECONDS_PER_DAY
            if age < older_than_days:
                continue
            size = sum(item.stat().st_size for item in child.rglob("*") if item.is_file())
            lock = child / LOCK_FILE
            in_use = False
            if lock.is_file():
                probe = _FileLock(lock)
                if probe.acquire():
                    probe.release()
                else:
                    in_use = True
            found.append(LeftoverWorkspace(child, size, age, in_use))
    return found


def remove_workspaces(workspaces: Iterable[LeftoverWorkspace]) -> list[Path]:
    """Delete the given folders, skipping any in use. Returns the paths that were removed."""
    import shutil

    removed = []
    for workspace in workspaces:
        if workspace.in_use:
            continue
        shutil.rmtree(workspace.path, ignore_errors=True)
        removed.append(workspace.path)
    return removed
