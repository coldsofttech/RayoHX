"""Reading and writing jobs in the database."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from rayohx.platform.jobs.model import (
    ACTIVE_STATES,
    JobRecord,
    JobSpec,
    JobState,
    QueuePriority,
    VerificationState,
)
from rayohx.platform.queue.scheduler import Candidate

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterable, Sequence

    from rayohx.platform.persistence import Database

#: Columns ``update`` and ``transition`` may set. Anything else is a bug, not user input.
_SETTABLE = frozenset(
    {
        "state",
        "priority",
        "rank",
        "attempts",
        "verification",
        "error_code",
        "error_message",
        "started_at",
        "finished_at",
        "output_path",
        "output_size",
        "not_before",
        "recovered",
        "needs_credentials",
        "control_request",
        "progress_json",
        "secret_ref",
        "result_json",
        "auto_paused",
    }
)
_ACTIVE_VALUES = tuple(s.value for s in ACTIVE_STATES)


def _marks(items: Sequence[object]) -> str:
    return ",".join("?" * len(items))


def _record(row: sqlite3.Row) -> JobRecord:
    progress = row["progress_json"]
    result = row["result_json"]
    return JobRecord(
        id=row["id"],
        url=row["url"],
        spec=JobSpec.from_json(row["spec_json"]),
        state=JobState(row["state"]),
        priority=QueuePriority(row["priority"]),
        rank=row["rank"],
        attempts=row["attempts"],
        verification=VerificationState(row["verification"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        output_path=row["output_path"],
        output_size=row["output_size"],
        not_before=row["not_before"],
        recovered=bool(row["recovered"]),
        needs_credentials=bool(row["needs_credentials"]),
        control_request=row["control_request"],
        profile_id=row["profile_id"],
        auto_paused=bool(row["auto_paused"]),
        result=json.loads(result) if result else None,
        progress=json.loads(progress) if progress else None,
    )


class JobRepository:
    """Every database operation the queue needs."""

    def __init__(self, database: Database, *, clock: Any = time.time) -> None:
        self._db = database
        self._clock = clock

    # --- reading ---------------------------------------------------------------------------

    def get(self, job_id: str) -> JobRecord | None:
        row = self._db.fetchone("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return _record(row) if row else None

    def select(
        self,
        *,
        states: Iterable[JobState] | None = None,
        limit: int | None = None,
        queue_order: bool = True,
    ) -> list[JobRecord]:
        """Jobs in queue order (priority, then rank), or newest first."""
        clauses = ""
        params: list[Any] = []
        if states is not None:
            values = [s.value for s in states]
            if not values:
                return []
            clauses = f"WHERE state IN ({_marks(values)})"
            params += values
        order = (
            "priority DESC, rank ASC, created_at ASC, id ASC"
            if queue_order
            else "created_at DESC, id DESC"
        )
        sql = f"SELECT * FROM jobs {clauses} ORDER BY {order}"  # noqa: S608
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return [_record(r) for r in self._db.fetchall(sql, params)]

    def counts(self) -> dict[str, int]:
        rows = self._db.fetchall("SELECT state, COUNT(*) AS n FROM jobs GROUP BY state")
        counts = {s.value: 0 for s in JobState}
        counts.update({r["state"]: r["n"] for r in rows})
        return counts

    def ready(self, now: float) -> list[Candidate]:
        """Queued jobs that could start at ``now``."""
        rows = self._db.fetchall(
            "SELECT id, priority, rank, created_at, not_before FROM jobs "
            "WHERE state = 'queued' AND needs_credentials = 0 "
            "AND (not_before IS NULL OR not_before <= ?)",
            (now,),
        )
        return [
            Candidate(r["id"], r["priority"], r["rank"], r["created_at"], r["not_before"])
            for r in rows
        ]

    def waiting_count(self) -> int:
        """Jobs that will run without anyone doing anything: queued (maybe delayed) or active."""
        row = self._db.fetchone(
            f"SELECT COUNT(*) AS n FROM jobs WHERE (state = 'queued' AND needs_credentials = 0) "  # noqa: S608
            f"OR state IN ({_marks(_ACTIVE_VALUES)})",
            _ACTIVE_VALUES,
        )
        return int(row["n"]) if row else 0

    def next_delay(self, now: float) -> float | None:
        """Seconds until the earliest delayed queued job is ready, if any."""
        row = self._db.fetchone(
            "SELECT MIN(not_before) AS t FROM jobs WHERE state = 'queued' "
            "AND needs_credentials = 0 AND not_before > ?",
            (now,),
        )
        return None if row is None or row["t"] is None else max(0.0, row["t"] - now)

    def control_requests(self) -> list[tuple[str, str]]:
        rows = self._db.fetchall(
            "SELECT id, control_request FROM jobs WHERE control_request IS NOT NULL"
        )
        return [(r["id"], r["control_request"]) for r in rows]

    def rank_bounds(self) -> tuple[float, float]:
        row = self._db.fetchone("SELECT MIN(rank) AS lo, MAX(rank) AS hi FROM jobs")
        if row is None or row["lo"] is None:
            return 0.0, 0.0
        return float(row["lo"]), float(row["hi"])

    def rank_below(self, priority: int, rank: float, *, exclude: str) -> float | None:
        """The largest rank under ``rank`` among jobs of ``priority``, not counting ``exclude``."""
        row = self._db.fetchone(
            "SELECT MAX(rank) AS r FROM jobs WHERE priority = ? AND rank < ? AND id != ?",
            (priority, rank, exclude),
        )
        return None if row is None or row["r"] is None else float(row["r"])

    def now(self) -> float:
        return float(self._clock())

    def add_workspace(self, job_id: str, path: str) -> None:
        """Remember that a job uses this working folder."""
        with self._db.transaction() as c:
            c.execute(
                "INSERT OR REPLACE INTO job_workspaces (job_id, path, seen_at) VALUES (?, ?, ?)",
                (job_id, path, self._clock()),
            )

    def workspace_owners(self) -> dict[str, str]:
        """Working folder path to the job that last used it."""
        rows = self._db.fetchall("SELECT path, job_id FROM job_workspaces ORDER BY seen_at ASC")
        return {r["path"]: r["job_id"] for r in rows}

    def workspaces_of(self, job_id: str) -> list[str]:
        rows = self._db.fetchall(
            "SELECT path FROM job_workspaces WHERE job_id = ? ORDER BY seen_at", (job_id,)
        )
        return [r["path"] for r in rows]

    def forget_workspace(self, path: str) -> None:
        with self._db.transaction() as c:
            c.execute("DELETE FROM job_workspaces WHERE path = ?", (path,))

    def auto_paused_ids(self) -> list[str]:
        rows = self._db.fetchall(
            "SELECT id FROM jobs WHERE state = 'paused' AND auto_paused = 1 "
            "ORDER BY priority DESC, rank ASC, created_at ASC"
        )
        return [r["id"] for r in rows]

    def finished_output_bytes(self) -> int:
        """The size of every output the completed jobs made."""
        row = self._db.fetchone(
            "SELECT COALESCE(SUM(output_size), 0) AS n FROM jobs WHERE state = 'completed'"
        )
        return int(row["n"]) if row else 0

    def peak_temporary_bytes(self) -> int:
        """The most working space any finished job used at one time."""
        peak = 0
        for row in self._db.fetchall("SELECT result_json FROM jobs WHERE result_json IS NOT NULL"):
            try:
                found = json.loads(row["result_json"]).get("storage", {})
            except ValueError:
                continue
            peak = max(peak, int(found.get("peak_temporary_bytes") or 0))
        return peak

    def attempts(self, job_id: str) -> list[dict[str, Any]]:
        rows = self._db.fetchall(
            "SELECT attempt, started_at, finished_at, outcome, error_code, error_message "
            "FROM job_attempts WHERE job_id = ? ORDER BY id",
            (job_id,),
        )
        return [dict(r) for r in rows]

    # --- writing ---------------------------------------------------------------------------

    def insert(
        self,
        *,
        job_id: str,
        spec: JobSpec,
        display_url: str,
        priority: QueuePriority,
        rank: float,
        secret_ref: str | None,
        profile_id: str | None = None,
    ) -> JobRecord:
        now = self._clock()
        with self._db.transaction() as c:
            c.execute(
                "INSERT INTO jobs (id, spec_json, state, priority, rank, created_at, updated_at, "
                "url, secret_ref, profile_id) VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    spec.to_json(),
                    int(priority),
                    rank,
                    now,
                    now,
                    display_url,
                    secret_ref,
                    profile_id,
                ),
            )
        record = self.get(job_id)
        assert record is not None  # noqa: S101
        return record

    def next_rank(self) -> float:
        return self.rank_bounds()[1] + 1.0

    def renumber(self) -> None:
        """Give every job a rank 1, 2, 3, ... in queue order (when ranks run out of room)."""
        rows = self._db.fetchall(
            "SELECT id FROM jobs ORDER BY priority DESC, rank ASC, created_at ASC, id ASC"
        )
        with self._db.transaction() as c:
            for position, row in enumerate(rows, start=1):
                c.execute("UPDATE jobs SET rank = ? WHERE id = ?", (float(position), row["id"]))

    def rank_of(self, job_id: str) -> float | None:
        row = self._db.fetchone("SELECT rank FROM jobs WHERE id = ?", (job_id,))
        return None if row is None else float(row["rank"])

    def secret_ref(self, job_id: str) -> str | None:
        row = self._db.fetchone("SELECT secret_ref FROM jobs WHERE id = ?", (job_id,))
        return row["secret_ref"] if row else None

    def transition(
        self, job_id: str, from_states: Iterable[JobState], to: JobState, **fields: Any
    ) -> bool:
        """Move a job only if it is still in one of ``from_states``. True if it moved."""
        sources = [s.value for s in from_states]
        return self._write(
            f"id = ? AND state IN ({_marks(sources)})", [job_id, *sources], state=to.value, **fields
        )

    def update(self, job_id: str, **fields: Any) -> bool:
        return self._write("id = ?", [job_id], **fields)

    def _write(self, where: str, where_params: list[Any], **fields: Any) -> bool:
        unknown = set(fields) - _SETTABLE
        if unknown:
            raise ValueError(f"cannot set {sorted(unknown)}")
        values = {k: (int(v) if isinstance(v, bool) else v) for k, v in fields.items()}
        values["updated_at"] = self._clock()
        assignments = ", ".join(f"{name} = ?" for name in values)
        sql = f"UPDATE jobs SET {assignments} WHERE {where}"  # noqa: S608
        with self._db.transaction() as c:
            return c.execute(sql, [*values.values(), *where_params]).rowcount > 0

    def delete(self, job_id: str) -> bool:
        with self._db.transaction() as c:
            return c.execute("DELETE FROM jobs WHERE id = ?", (job_id,)).rowcount > 0

    def recover_active(self) -> list[str]:
        """Return jobs a crashed runner left half way to the queue. Returns their ids."""
        with self._db.transaction() as c:
            rows = c.execute(
                f"SELECT id FROM jobs WHERE state IN ({_marks(_ACTIVE_VALUES)})",  # noqa: S608
                _ACTIVE_VALUES,
            ).fetchall()
            ids = [r["id"] for r in rows]
            if ids:
                c.execute(
                    f"UPDATE jobs SET state = 'queued', recovered = 1, control_request = NULL, "  # noqa: S608
                    f"updated_at = ? WHERE id IN ({_marks(ids)})",
                    [self._clock(), *ids],
                )
        return ids

    def begin_attempt(self, job_id: str, attempt: int) -> int:
        with self._db.transaction() as c:
            cursor = c.execute(
                "INSERT INTO job_attempts (job_id, attempt, started_at) VALUES (?, ?, ?)",
                (job_id, attempt, self._clock()),
            )
            return int(cursor.lastrowid or 0)

    def end_attempt(
        self, attempt_id: int, outcome: str, code: str | None, message: str | None
    ) -> None:
        with self._db.transaction() as c:
            c.execute(
                "UPDATE job_attempts SET finished_at = ?, outcome = ?, error_code = ?, "
                "error_message = ? WHERE id = ?",
                (self._clock(), outcome, code, message, attempt_id),
            )
