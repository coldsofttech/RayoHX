"""``Rayo``: the single entry point to the platform.

It owns the shared foundations (folders, database, events, settings) and the persistent download
queue. Profiles, scheduling, diagnostics and storage services are added as they are built.

    from rayohx import Rayo

    with Rayo() as rayo:
        rayo.events.emit("example.hello")
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Self

from rayohx.downloader import Downloader
from rayohx.platform.events import EventBus, EventCategory, EventStore, Severity
from rayohx.platform.paths import PlatformPaths, resolve_paths, under
from rayohx.platform.persistence import Database, SettingsStore
from rayohx.platform.profiles import ProfileStore
from rayohx.platform.queue import JobRepository, Queue, QueueRunner
from rayohx.platform.secrets import SecretStore, default_secret_store

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
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
        download_dir: Path | str | None = None,
        secrets: SecretStore | None = None,
        max_active: int = 2,
        downloader_factory: Callable[..., Downloader] = Downloader,
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
        env = os.environ if environ is None else environ
        configured = download_dir if download_dir is not None else env.get("RAYOHX_DOWNLOAD_DIR")
        #: Where finished files go unless a job names another folder.
        self.download_dir = (
            Path(configured).expanduser() if configured else Path.home() / "Downloads" / "RayoHX"
        )
        self.secrets: SecretStore = secrets if secrets is not None else default_secret_store()
        lock_path = self.paths.data_dir / "runner.lock"
        #: The built-in and saved download profiles.
        self.profiles = ProfileStore(self.database, self.settings)
        self.jobs = JobRepository(self.database)
        runner = QueueRunner(
            self.jobs,
            self.events,
            self.secrets,
            download_dir=self.download_dir,
            lock_path=lock_path,
            max_active=max_active,
            downloader_factory=downloader_factory,
        )
        #: The persistent download queue. Call ``queue.start()`` to run jobs in this process.
        self.queue = Queue(
            self.jobs,
            runner,
            self.events,
            self.secrets,
            self.settings,
            self.profiles,
            download_dir=self.download_dir,
            runner_lock_path=lock_path,
        )
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
        """Stop the queue if it runs here and release the database. Safe to call twice."""
        if self.queue.running:
            self.queue.stop()
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
