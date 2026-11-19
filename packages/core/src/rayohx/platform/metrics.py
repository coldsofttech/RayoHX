"""Numbers about the platform: how much is queued, downloaded, failed, verified and stored.

All counts come from the database, so they survive a restart; rates and byte counts of running
downloads come from their live progress. ``to_prometheus`` writes the same numbers in the text
format monitoring tools read.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from rayohx.platform.jobs.model import JobState

if TYPE_CHECKING:
    from rayohx.platform.persistence import Database
    from rayohx.platform.queue.queue import Queue
    from rayohx.platform.storage.service import StorageService


def collect_metrics(
    database: Database, queue: Queue, storage: StorageService, *, now: float | None = None
) -> dict[str, Any]:
    """The platform's numbers right now."""
    moment = time.time() if now is None else now
    stats = queue.stats()
    counts = stats["counts"]
    live = list(queue.list(states=[s for s in JobState if s.is_active]))
    speed = sum(float((j.progress or {}).get("speed") or 0) for j in live)
    downloaded_live = sum(int((j.progress or {}).get("downloaded_bytes") or 0) for j in live)

    def scalar(sql: str, params: tuple[Any, ...] = ()) -> float:
        row = database.fetchone(sql, params)
        return float(row[0] or 0) if row else 0.0

    verification = {
        r["verification"]: r["n"]
        for r in database.fetchall(
            "SELECT verification, COUNT(*) AS n FROM jobs GROUP BY verification"
        )
    }
    checksums = {"verified": 0, "failed": 0}
    for row in database.fetchall("SELECT result_json FROM jobs WHERE result_json IS NOT NULL"):
        if '"checksum"' not in row["result_json"]:
            continue
        try:
            sums = (json.loads(row["result_json"]).get("integrity") or {}).get("checksum")
        except ValueError:
            continue
        if sums and sums.get("matches") is True:
            checksums["verified"] += 1
        elif sums and sums.get("matches") is False:
            checksums["failed"] += 1
    snapshot = storage.snapshot()
    free = next((v.usage.free_bytes for v in snapshot.volumes if v.role == "downloads"), None)
    oldest = scalar("SELECT MIN(created_at) FROM jobs WHERE state = 'queued'")
    return {
        "queue": {
            "queued": counts["queued"],
            "active": stats["active"],
            "completed": counts["completed"],
            "failed": counts["failed"],
            "paused": counts["paused"],
            "cancelled": counts["cancelled"],
            "max_active": stats["max_active"],
            "oldest_queued_seconds": round(moment - oldest, 1) if oldest else 0.0,
            "average_duration_seconds": round(
                scalar(
                    "SELECT AVG(finished_at - started_at) FROM jobs "
                    "WHERE state = 'completed' AND started_at IS NOT NULL "
                    "AND finished_at IS NOT NULL"
                ),
                2,
            ),
        },
        "downloads": {
            "bytes_downloaded_active": downloaded_live,
            "bytes_written_total": int(
                scalar("SELECT COALESCE(SUM(output_size), 0) FROM jobs WHERE state = 'completed'")
            ),
            "throughput_bytes_per_second": round(speed, 1),
            "segments_completed_active": sum(
                int((j.progress or {}).get("completed_segments") or 0) for j in live
            ),
            "retries": int(scalar("SELECT COUNT(*) FROM job_attempts WHERE outcome = 'failed'")),
            "failures": counts["failed"],
        },
        "storage": {
            "level": snapshot.level.name.lower(),
            "free_bytes": free,
            "output_bytes": snapshot.output_bytes,
            "workspace_bytes": snapshot.workspace_bytes,
            "incomplete_bytes": snapshot.incomplete_bytes,
            "reserved_bytes": snapshot.reserved_bytes,
            "peak_temporary_bytes": snapshot.peak_temporary_bytes,
        },
        "verification": {
            "verified": verification.get("verified", 0),
            "failed": verification.get("failed", 0),
            "not_requested": verification.get("not_requested", 0),
            "checksums_matched": checksums["verified"],
            "checksums_mismatched": checksums["failed"],
        },
        "automation": {"triggered": 0, "succeeded": 0, "failed": 0},
    }


def to_prometheus(metrics: dict[str, Any], prefix: str = "rayohx") -> str:
    """The numbers in Prometheus text format. Names are ``rayohx_<section>_<name>``."""
    lines: list[str] = []
    for section, values in metrics.items():
        for name, value in values.items():
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, str):
                lines.append(f'{prefix}_{section}_{name}{{value="{value}"}} 1')
                continue
            lines.append(f"{prefix}_{section}_{name} {value}")
    return "\n".join(lines) + "\n"
