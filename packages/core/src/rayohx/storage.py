"""Working folders left on disk by downloads: finding them, measuring them, cleaning them up.

A download keeps its resume state in a private working folder. This module lets front ends list
those folders and remove abandoned ones without knowing how the engine lays them out. A folder
that a running download holds is never reported as removable, and nothing outside the folders
found here is ever touched, so a finished output file is safe.
"""

from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from rayohx._download._workspace import FOLDER_PREFIX, LOCK_FILE, STATE_FILE, _FileLock

__all__ = [
    "WorkspaceInfo",
    "clean_workspaces",
    "find_workspaces",
    "folder_size",
    "inspect_workspace",
    "is_workspace_in_use",
    "last_used",
]

_KEY_FOLDER = re.compile(r"^[0-9a-f]{16}$")
_DAY = 86400


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkspaceInfo:
    """One working folder."""

    path: Path
    size_bytes: int
    age_days: float
    in_use: bool

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def safe_to_remove(self) -> bool:
        """Whether no running download holds the folder."""
        return not self.in_use


def find_workspaces(folder: Path | str) -> list[Path]:
    """Working folders directly inside ``folder``.

    ``.rayohx-*`` folders, and the hash-named ones inside a ``workspace_dir`` (they hold a resume
    state file). Symbolic links are never followed.
    """
    root = Path(folder)
    try:
        children = sorted(root.iterdir())
    except OSError:
        return []
    found = []
    for child in children:
        if child.is_symlink() or not child.is_dir():
            continue
        named = child.name.startswith(FOLDER_PREFIX)
        keyed = bool(_KEY_FOLDER.match(child.name)) and (child / STATE_FILE).is_file()
        if named or keyed:
            found.append(child)
    return found


def folder_size(folder: Path | str) -> int:
    """Bytes in the files under ``folder``. Files that vanish while counting are ignored."""
    total = 0
    for item in Path(folder).rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def last_used(folder: Path | str) -> float:
    """When the folder's resume state (or the folder itself) last changed, as a timestamp."""
    path = Path(folder)
    state = path / STATE_FILE
    return (state if state.is_file() else path).stat().st_mtime


def is_workspace_in_use(folder: Path | str) -> bool:
    """Whether a running download holds this folder's lock."""
    lock = Path(folder) / LOCK_FILE
    if not lock.is_file():
        return False
    probe = _FileLock(lock)
    if probe.acquire():
        probe.release()
        return False
    return True


def inspect_workspace(folder: Path | str, *, now: float | None = None) -> WorkspaceInfo:
    """Measure one working folder."""
    path = Path(folder)
    moment = time.time() if now is None else now
    return WorkspaceInfo(
        path=path,
        size_bytes=folder_size(path),
        age_days=max(0.0, (moment - last_used(path)) / _DAY),
        in_use=is_workspace_in_use(path),
    )


def clean_workspaces(
    folder: Path | str,
    *,
    older_than_days: float = 0,
    dry_run: bool = False,
    now: float | None = None,
) -> tuple[list[WorkspaceInfo], int]:
    """Remove working folders in ``folder`` that are not in use and old enough.

    Returns the folders removed (or, with ``dry_run``, that would be) and the number skipped
    because a running download holds them.
    """
    removed: list[WorkspaceInfo] = []
    skipped = 0
    for path in find_workspaces(folder):
        try:
            info = inspect_workspace(path, now=now)
        except OSError:
            continue
        if info.in_use:
            skipped += 1
            continue
        if info.age_days < older_than_days:
            continue
        removed.append(info)
        if not dry_run:
            shutil.rmtree(path, ignore_errors=True)
    return removed, skipped
