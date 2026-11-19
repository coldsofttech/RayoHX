"""The diagnostic reports that were saved, so they can be listed and cleaned up."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from rayohx.platform.persistence import Database


class ReportRegistry:
    """A list, in the database, of the report files that were written."""

    def __init__(self, database: Database, *, clock: Callable[[], float] = time.time) -> None:
        self._db = database
        self._clock = clock

    def add(self, path: Path, *, job_id: str | None, summary: str) -> int:
        with self._db.transaction() as c:
            cursor = c.execute(
                "INSERT INTO diagnostic_reports (created_at, job_id, path, size_bytes, summary) "
                "VALUES (?, ?, ?, ?, ?)",
                (self._clock(), job_id, str(path), path.stat().st_size, summary[:500]),
            )
            return int(cursor.lastrowid or 0)

    def entries(self) -> list[tuple[int, Path, float]]:
        """Each saved report as ``(id, path, created)``, oldest first."""
        rows = self._db.fetchall(
            "SELECT id, path, created_at FROM diagnostic_reports ORDER BY created_at"
        )
        return [(r["id"], Path(r["path"]), r["created_at"]) for r in rows]

    def listing(self, limit: int = 50) -> list[dict[str, object]]:
        rows = self._db.fetchall(
            "SELECT id, created_at, job_id, path, size_bytes, summary FROM diagnostic_reports "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [
            {
                "id": r["id"], "created_at": r["created_at"], "job_id": r["job_id"],
                "name": Path(r["path"]).name, "size_bytes": r["size_bytes"],
                "summary": r["summary"],
            }
            for r in rows
        ]  # fmt: skip

    def forget(self, report_id: int) -> None:
        with self._db.transaction() as c:
            c.execute("DELETE FROM diagnostic_reports WHERE id = ?", (report_id,))
