"""The database schema, as an ordered list of migrations.

Rules:

* Versions start at 1 and have no gaps. Never edit or reorder a migration that has shipped;
  add a new one.
* A migration is plain SQL that only creates or alters things. It runs inside one transaction, so
  a failure leaves the database as it was.
* The version is stored in ``PRAGMA user_version`` and each applied migration is also recorded in
  ``schema_migrations``, a table the runner creates itself.

The migrations are code, not data files, so they are present in every packaged build.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NAME = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str

    def __post_init__(self) -> None:
        if self.version < 1 or not _NAME.match(self.name):
            raise ValueError(f"invalid migration {self.version}:{self.name}")


_INITIAL = """
CREATE TABLE settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE jobs (
    id            TEXT PRIMARY KEY,
    spec_json     TEXT NOT NULL,
    state         TEXT NOT NULL,
    priority      INTEGER NOT NULL DEFAULT 1,
    rank          REAL NOT NULL DEFAULT 0,
    attempts      INTEGER NOT NULL DEFAULT 0,
    verification  TEXT NOT NULL DEFAULT 'not_requested',
    result_json   TEXT,
    error_code    TEXT,
    error_message TEXT,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL,
    started_at    REAL,
    finished_at   REAL
);
CREATE INDEX jobs_state_priority ON jobs (state, priority DESC, rank, created_at);

CREATE TABLE job_attempts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        TEXT NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    attempt       INTEGER NOT NULL,
    started_at    REAL NOT NULL,
    finished_at   REAL,
    outcome       TEXT,
    error_code    TEXT,
    error_message TEXT,
    detail_json   TEXT
);
CREATE INDEX job_attempts_job ON job_attempts (job_id, attempt);

CREATE TABLE events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             REAL NOT NULL,
    type           TEXT NOT NULL,
    category       TEXT NOT NULL,
    severity       INTEGER NOT NULL,
    job_id         TEXT,
    correlation_id TEXT,
    payload_json   TEXT NOT NULL
);
CREATE INDEX events_job ON events (job_id, id);
CREATE INDEX events_category ON events (category, id);
CREATE INDEX events_ts ON events (ts);
"""

_QUEUE = """
ALTER TABLE jobs ADD COLUMN url TEXT NOT NULL DEFAULT '';
ALTER TABLE jobs ADD COLUMN secret_ref TEXT;
ALTER TABLE jobs ADD COLUMN needs_credentials INTEGER NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN recovered INTEGER NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN output_path TEXT;
ALTER TABLE jobs ADD COLUMN output_size INTEGER;
ALTER TABLE jobs ADD COLUMN not_before REAL;
ALTER TABLE jobs ADD COLUMN control_request TEXT;
ALTER TABLE jobs ADD COLUMN progress_json TEXT;
CREATE INDEX jobs_ready ON jobs (state, not_before);
"""

#: Every migration this version of RayoHX knows, oldest first.
MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "initial", _INITIAL),
    Migration(2, "queue", _QUEUE),
)


def latest_version(migrations: tuple[Migration, ...] = MIGRATIONS) -> int:
    return migrations[-1].version if migrations else 0


def check_sequence(migrations: tuple[Migration, ...]) -> None:
    """Raise ``ValueError`` unless the versions are 1, 2, 3, ... with no gaps."""
    for expected, migration in enumerate(migrations, start=1):
        if migration.version != expected:
            raise ValueError(
                f"migration versions must be 1, 2, 3, ...; found {migration.version} "
                f"where {expected} was expected"
            )
