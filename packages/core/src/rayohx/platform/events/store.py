"""Saving events in the database and reading them back."""

from __future__ import annotations

import dataclasses
import json
from typing import TYPE_CHECKING

from rayohx.platform.events.model import EventCategory, PlatformEvent, Severity

if TYPE_CHECKING:
    import sqlite3

    from rayohx.platform.persistence import Database

MAX_PAGE = 1000


def _from_row(row: sqlite3.Row) -> PlatformEvent:
    return PlatformEvent(
        id=row["id"],
        timestamp=row["ts"],
        type=row["type"],
        category=EventCategory(row["category"]),
        severity=Severity(row["severity"]),
        job_id=row["job_id"],
        correlation_id=row["correlation_id"],
        payload=json.loads(row["payload_json"]),
    )


class EventStore:
    """An append-only log of platform events."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def append(self, event: PlatformEvent) -> PlatformEvent:
        """Save ``event`` and return it with its ``id`` set."""
        with self._db.transaction() as connection:
            cursor = connection.execute(
                "INSERT INTO events (ts, type, category, severity, job_id, correlation_id, "
                "payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event.timestamp,
                    event.type,
                    event.category.value,
                    int(event.severity),
                    event.job_id,
                    event.correlation_id,
                    json.dumps(dict(event.payload), sort_keys=True),
                ),
            )
            return dataclasses.replace(event, id=cursor.lastrowid)

    def query(
        self,
        *,
        job_id: str | None = None,
        category: EventCategory | None = None,
        min_severity: Severity | None = None,
        after_id: int | None = None,
        limit: int = 100,
        newest_first: bool = False,
    ) -> list[PlatformEvent]:
        """Events matching every given filter.

        ``after_id`` returns events saved after that one, oldest first: a client that remembers
        the last id it saw can follow the log without gaps or repeats.
        """
        clauses = []
        params: list[object] = []
        if job_id is not None:
            clauses.append("job_id = ?")
            params.append(job_id)
        if category is not None:
            clauses.append("category = ?")
            params.append(category.value)
        if min_severity is not None:
            clauses.append("severity >= ?")
            params.append(int(min_severity))
        if after_id is not None:
            clauses.append("id > ?")
            params.append(after_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = "DESC" if newest_first and after_id is None else "ASC"
        params.append(max(1, min(limit, MAX_PAGE)))
        sql = f"SELECT * FROM events {where} ORDER BY id {order} LIMIT ?"  # noqa: S608
        rows = self._db.fetchall(sql, params)
        return [_from_row(row) for row in rows]

    def last_id(self) -> int:
        row = self._db.fetchone("SELECT COALESCE(MAX(id), 0) AS last FROM events")
        return int(row["last"]) if row else 0

    def count(self, *, job_id: str | None = None) -> int:
        if job_id is None:
            row = self._db.fetchone("SELECT COUNT(*) AS n FROM events")
        else:
            row = self._db.fetchone("SELECT COUNT(*) AS n FROM events WHERE job_id = ?", (job_id,))
        return int(row["n"]) if row else 0

    def prune(self, *, older_than: float | None = None, keep_last: int | None = None) -> int:
        """Delete old events; return how many went.

        ``older_than`` is a timestamp: events before it are removed. ``keep_last`` keeps only the
        newest that many. With both, an event is removed if either rule says so.
        """
        deleted = 0
        with self._db.transaction() as connection:
            if older_than is not None:
                deleted += connection.execute(
                    "DELETE FROM events WHERE ts < ?", (older_than,)
                ).rowcount
            if keep_last is not None:
                deleted += connection.execute(
                    "DELETE FROM events WHERE id <= (SELECT COALESCE(MAX(id), 0) FROM events) - ?",
                    (max(0, keep_last),),
                ).rowcount
        return deleted
