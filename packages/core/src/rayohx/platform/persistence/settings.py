"""Small named values kept in the database, stored as JSON."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rayohx.platform.persistence.database import Database


class SettingsStore:
    """A key-value store. Values must be JSON-serializable and must not hold secrets."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def get(self, key: str, default: Any = None) -> Any:
        row = self._db.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        return default if row is None else json.loads(row["value"])

    def set(self, key: str, value: Any) -> None:
        text = json.dumps(value, sort_keys=True)
        with self._db.transaction() as connection:
            connection.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                (key, text, time.time()),
            )

    def delete(self, key: str) -> bool:
        with self._db.transaction() as connection:
            return connection.execute("DELETE FROM settings WHERE key = ?", (key,)).rowcount > 0

    def all(self) -> dict[str, Any]:
        rows = self._db.fetchall("SELECT key, value FROM settings ORDER BY key")
        return {row["key"]: json.loads(row["value"]) for row in rows}
