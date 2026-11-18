"""``Rayo``: the single entry point to the platform.

Phase 2-1 gives it the shared foundations (folders, database, events, settings). The queue,
profiles, scheduling, diagnostics and storage services are added to this class as they are built.

    from rayohx import Rayo

    with Rayo() as rayo:
        rayo.events.emit("example.hello")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Self

from rayohx.platform.events import EventBus, EventCategory, EventStore, Severity
from rayohx.platform.paths import PlatformPaths, resolve_paths, under
from rayohx.platform.persistence import Database, SettingsStore

if TYPE_CHECKING:
    from collections.abc import Mapping
    from types import TracebackType

logger = logging.getLogger(__name__)


class Rayo:
    """The platform: folders, the database, events and settings.

    Create it with no arguments for the user's own folders, or give ``home`` to keep everything
    under one folder (tests and portable use). Close it, or use it as a context manager, to
    release the database.
    """

    def __init__(
        self,
        *,
        home: Path | str | None = None,
        paths: PlatformPaths | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        if paths is not None:
            self.paths = paths
        elif home is not None:
            self.paths = under(Path(home), "home")
        else:
            self.paths = resolve_paths(environ)
        self.paths.ensure()
        self.database = Database(self.paths.database_path, backup_dir=self.paths.backups_dir)
        self.settings = SettingsStore(self.database)
        self.event_store = EventStore(self.database)
        self.events = EventBus(self.event_store)
        self._announce_start()

    def _announce_start(self) -> None:
        if self.database.recovered_from is not None:
            self.events.emit(
                "system.database_recovered",
                category=EventCategory.SYSTEM,
                severity=Severity.WARNING,
                moved_to=self.database.recovered_from,
            )
        if self.database.backup_path is not None:
            self.events.emit(
                "system.database_migrated",
                category=EventCategory.SYSTEM,
                backup=self.database.backup_path,
                schema_version=self.database.schema_version,
            )

    @property
    def schema_version(self) -> int:
        """The version of the database schema in use."""
        return self.database.schema_version

    def close(self) -> None:
        """Release the database. Safe to call more than once."""
        self.database.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
