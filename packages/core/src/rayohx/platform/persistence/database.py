"""The platform's SQLite database: connections, transactions, migrations and recovery.

* One connection per thread, in WAL mode, so readers never block the writer.
* ``transaction()`` takes the write lock up front (``BEGIN IMMEDIATE``), so two writers wait for
  each other instead of failing half way.
* Opening a database brings it to the latest schema. Before changing a database that already
  holds data, a copy is saved next to the backups.
* A file that is not a database, or fails SQLite's integrity check, is moved aside (not deleted)
  and a fresh database is created, so a damaged file never stops the application from starting.
* A database written by a newer RayoHX is refused and left untouched.

SQLite's write-ahead log needs a local disk: do not put the database on a network share.
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from rayohx.platform.errors import PersistenceError, SchemaTooNewError
from rayohx.platform.persistence.migrations import (
    MIGRATIONS,
    Migration,
    check_sequence,
    latest_version,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from types import TracebackType

logger = logging.getLogger(__name__)

BUSY_TIMEOUT_MS = 10_000


def _is_corruption(exc: sqlite3.DatabaseError) -> bool:
    """Whether ``exc`` means the file is damaged, as opposed to busy, locked or read-only."""
    if isinstance(exc, sqlite3.OperationalError):
        return False
    text = str(exc).lower()
    return "malformed" in text or "not a database" in text or type(exc) is sqlite3.DatabaseError


def _statements(script: str) -> Iterator[str]:
    """Split ``script`` into complete SQL statements."""
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            buffer = ""
            if statement:
                yield statement
    if buffer.strip():
        raise PersistenceError("A migration ends in the middle of a statement.")


class Database:
    """An open, migrated database. Safe to use from many threads."""

    def __init__(
        self,
        path: Path | str,
        *,
        migrations: Sequence[Migration] = MIGRATIONS,
        backup_dir: Path | str | None = None,
        recover: bool = True,
    ) -> None:
        self.path = Path(path)
        self._migrations = tuple(migrations)
        check_sequence(self._migrations)
        self._backup_dir = Path(backup_dir) if backup_dir is not None else self.path.parent
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._lock = threading.Lock()
        #: Held while a statement or transaction runs, so ``close`` never closes a connection
        #: that another thread is in the middle of using.
        self._gate = threading.RLock()
        self._closed = False
        #: Where a damaged database was moved to, if one had to be replaced.
        self.recovered_from: Path | None = None
        #: The copy saved before the schema was changed, if one was.
        self.backup_path: Path | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._open(recover=recover)

    # --- opening ---------------------------------------------------------------------------

    def _open(self, *, recover: bool) -> None:
        try:
            self._prepare()
        except SchemaTooNewError:
            self.close()
            raise
        except sqlite3.DatabaseError as exc:
            self._drop_connections()
            if not (recover and _is_corruption(exc)):
                raise PersistenceError(f"The database could not be opened: {exc}") from exc
            self.recovered_from = self._quarantine()
            logger.warning("The database was damaged and moved to %s.", self.recovered_from)
            self._prepare()

    def _prepare(self) -> None:
        existed = self.path.is_file() and self.path.stat().st_size > 0
        connection = self.connection()
        if existed:
            row = connection.execute("PRAGMA quick_check").fetchone()
            if row is None or row[0] != "ok":
                raise sqlite3.DatabaseError("database disk image is malformed")
        connection.execute("PRAGMA journal_mode=WAL")
        self._migrate(connection, had_data=existed)

    def _quarantine(self) -> Path:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
        counter = 1
        while target.exists():
            counter += 1
            target = self.path.with_name(f"{self.path.name}.corrupt-{stamp}-{counter}")
        self.path.replace(target)
        for suffix in ("-wal", "-shm"):
            side = self.path.with_name(self.path.name + suffix)
            with contextlib.suppress(OSError):
                if side.exists():
                    side.replace(target.with_name(target.name + suffix))
        return target

    def _migrate(self, connection: sqlite3.Connection, *, had_data: bool) -> None:
        current = self._version(connection)
        latest = latest_version(self._migrations)
        if current > latest:
            raise SchemaTooNewError(current, latest)
        if current == latest:
            return
        if had_data and current > 0:
            self.backup_path = self._backup(connection, current)
        for migration in self._migrations:
            if migration.version > current:
                self._apply(connection, migration)

    @staticmethod
    def _version(connection: sqlite3.Connection) -> int:
        return int(connection.execute("PRAGMA user_version").fetchone()[0])

    def _backup(self, connection: sqlite3.Connection, version: int) -> Path:
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = self._backup_dir / f"{self.path.stem}-v{version}-{stamp}.bak"
        counter = 1
        while target.exists():
            counter += 1
            target = self._backup_dir / f"{self.path.stem}-v{version}-{stamp}-{counter}.bak"
        copy = sqlite3.connect(target)
        try:
            connection.backup(copy)
        finally:
            copy.close()
        return target

    def _apply(self, connection: sqlite3.Connection, migration: Migration) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            # Another process may have migrated while this one waited for the write lock.
            if self._version(connection) >= migration.version:
                connection.execute("ROLLBACK")
                return
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at REAL NOT NULL)"
            )
            for statement in _statements(migration.sql):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                (migration.version, migration.name, time.time()),
            )
            connection.execute(f"PRAGMA user_version = {int(migration.version)}")
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise

    # --- using -----------------------------------------------------------------------------

    @property
    def schema_version(self) -> int:
        return self._version(self.connection())

    def connection(self) -> sqlite3.Connection:
        """This thread's connection, opened on first use."""
        if self._closed:
            raise PersistenceError("The database is closed.")
        connection: sqlite3.Connection | None = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(
                self.path, isolation_level=None, check_same_thread=False, timeout=30
            )
            connection.row_factory = sqlite3.Row
            connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA synchronous = NORMAL")
            self._local.connection = connection
            with self._lock:
                self._connections.append(connection)
        return connection

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block as one atomic write. Raises if this thread is already in a transaction."""
        with self._gate:
            connection = self.connection()
            if connection.in_transaction:
                raise PersistenceError("A transaction is already open on this thread.")
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.execute("ROLLBACK")
                raise
            else:
                connection.execute("COMMIT")

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        """Run one statement outside any explicit transaction."""
        with self._gate:
            return self.connection().execute(sql, params)

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._gate:
            return self.connection().execute(sql, params).fetchall()

    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        with self._gate:
            row: sqlite3.Row | None = self.connection().execute(sql, params).fetchone()
        return row

    # --- closing ---------------------------------------------------------------------------

    def _drop_connections(self) -> None:
        with self._lock:
            connections, self._connections = self._connections, []
        for connection in connections:
            with contextlib.suppress(sqlite3.Error):
                connection.close()
        self._local = threading.local()

    def close(self) -> None:
        """Close every connection once running statements are done. Safe to call twice."""
        with self._gate:
            self._closed = True
            self._drop_connections()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
