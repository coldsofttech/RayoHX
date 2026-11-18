"""Where the platform keeps its files, including portable mode.

Order of precedence:

1. ``RAYOHX_HOME``: everything lives under that folder (``config``, ``data``, ``cache``).
2. Portable mode: a file named ``rayohx.portable`` beside the program (a frozen build) keeps
   everything in ``rayohx-data`` next to it, so the folder can be moved or run from a USB stick.
3. The per-user folders of the system (the same config folder the command line already uses).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

PORTABLE_MARKER = "rayohx.portable"
PORTABLE_FOLDER = "rayohx-data"
HOME_VARIABLE = "RAYOHX_HOME"
DATABASE_NAME = "rayohx.db"


@dataclass(frozen=True, slots=True, kw_only=True)
class PlatformPaths:
    """The folders the platform uses."""

    config_dir: Path
    data_dir: Path
    cache_dir: Path
    #: ``home``, ``portable`` or ``user``: which rule chose these folders.
    source: str = "user"

    @property
    def portable(self) -> bool:
        return self.source == "portable"

    @property
    def database_path(self) -> Path:
        return self.data_dir / DATABASE_NAME

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    def ensure(self) -> None:
        """Create the folders, readable only by the current user where the system allows."""
        for folder in (self.config_dir, self.data_dir, self.cache_dir):
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)


def under(root: Path, source: str) -> PlatformPaths:
    return PlatformPaths(
        config_dir=root / "config", data_dir=root / "data", cache_dir=root / "cache", source=source
    )


def resolve_paths(
    environ: Mapping[str, str] | None = None,
    *,
    executable: Path | str | None = None,
    frozen: bool | None = None,
) -> PlatformPaths:
    """Choose the platform folders. Nothing is created; call ``ensure`` for that.

    ``executable`` and ``frozen`` exist for tests. By default the running program is used, and
    portable mode applies only to a frozen (installed or packaged) build.
    """
    env = os.environ if environ is None else environ
    home = env.get(HOME_VARIABLE)
    if home:
        return under(Path(home).expanduser(), "home")

    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if is_frozen:
        program = Path(executable if executable is not None else sys.executable).resolve().parent
        if (program / PORTABLE_MARKER).is_file():
            return under(program / PORTABLE_FOLDER, "portable")

    if os.name == "nt":
        roaming = Path(env.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        local = Path(env.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return PlatformPaths(
            config_dir=roaming / "rayohx",
            data_dir=local / "rayohx",
            cache_dir=local / "rayohx" / "cache",
        )
    config = Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    data = Path(env.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    cache = Path(env.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return PlatformPaths(
        config_dir=config / "rayohx", data_dir=data / "rayohx", cache_dir=cache / "rayohx"
    )
