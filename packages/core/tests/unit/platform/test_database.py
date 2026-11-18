import sqlite3
import threading
from pathlib import Path

import pytest

from rayohx.platform.errors import PersistenceError, SchemaTooNewError
from rayohx.platform.persistence import (
    MIGRATIONS,
    Database,
    Migration,
    SettingsStore,
    latest_version,
)
from rayohx.platform.persistence.migrations import check_sequence

V1 = Migration(1, "one", "CREATE TABLE thing (id INTEGER PRIMARY KEY, name TEXT);")
V2 = Migration(2, "two", "ALTER TABLE thing ADD COLUMN size INTEGER NOT NULL DEFAULT 0;")


def scalar(db: Database, sql: str) -> object:
    row = db.fetchone(sql)
    assert row is not None
    return row[0]


def failing_write(db: Database) -> None:
    with db.transaction() as c:
        c.execute("INSERT INTO settings VALUES ('b', '2', 0)")
        raise RuntimeError


def tables(db: Database) -> set[str]:
    return {r["name"] for r in db.fetchall("SELECT name FROM sqlite_master WHERE type='table'")}


def test_a_new_database_gets_the_whole_schema(tmp_path: Path) -> None:
    with Database(tmp_path / "x.db") as db:
        assert db.schema_version == latest_version()
        assert {"jobs", "job_attempts", "events", "settings", "schema_migrations"} <= tables(db)
        assert scalar(db, "PRAGMA journal_mode") == "wal"
        assert scalar(db, "PRAGMA foreign_keys") == 1
        applied = db.fetchall("SELECT version, name FROM schema_migrations")
        assert [(r["version"], r["name"]) for r in applied] == [
            (m.version, m.name) for m in MIGRATIONS
        ]
        assert db.backup_path is None
        assert db.recovered_from is None


def test_opening_again_changes_nothing_and_makes_no_backup(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    Database(path).close()
    with Database(path, backup_dir=tmp_path / "bak") as db:
        assert db.backup_path is None
    assert not (tmp_path / "bak").exists()


def test_upgrading_keeps_data_and_saves_a_backup(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    with Database(path, migrations=[V1]) as db, db.transaction() as c:
        c.execute("INSERT INTO thing (name) VALUES ('keep')")
    with Database(path, migrations=[V1, V2], backup_dir=tmp_path / "bak") as db:
        assert db.schema_version == 2
        assert scalar(db, "SELECT name, size FROM thing") == "keep"
        assert db.backup_path is not None
        assert db.backup_path.parent == tmp_path / "bak"
        assert "-v1-" in db.backup_path.name
    old = sqlite3.connect(db.backup_path)
    try:
        assert old.execute("PRAGMA user_version").fetchone()[0] == 1
        assert old.execute("SELECT name FROM thing").fetchone()[0] == "keep"
    finally:
        old.close()


def test_a_failed_migration_rolls_back_completely(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    Database(path, migrations=[V1]).close()
    broken = Migration(
        2, "broken", "CREATE TABLE half (id INTEGER);\nINSERT INTO nowhere VALUES (1);"
    )
    with pytest.raises(PersistenceError):
        Database(path, migrations=[V1, broken], backup_dir=tmp_path / "bak")
    with Database(path, migrations=[V1]) as db:
        assert db.schema_version == 1
        assert "half" not in tables(db)


def test_a_database_from_a_newer_version_is_refused_and_untouched(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    Database(path, migrations=[V1, V2]).close()
    before = path.read_bytes()
    with pytest.raises(SchemaTooNewError) as caught:
        Database(path, migrations=[V1])
    assert (caught.value.found, caught.value.supported) == (2, 1)
    assert not list(tmp_path.glob("*.corrupt-*"))
    assert path.exists()
    assert path.read_bytes()[:16] == before[:16]


def test_a_file_that_is_not_a_database_is_moved_aside(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    path.write_bytes(b"this is definitely not sqlite" * 100)
    with Database(path) as db:
        assert db.recovered_from is not None
        assert db.recovered_from.read_bytes().startswith(b"this is definitely")
        assert db.schema_version == latest_version()


def test_recovery_can_be_switched_off(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    path.write_bytes(b"garbage" * 500)
    with pytest.raises(PersistenceError):
        Database(path, recover=False)
    assert path.read_bytes().startswith(b"garbage")


def test_a_damaged_page_is_caught_by_the_integrity_check(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    with Database(path) as db:
        with db.transaction() as c:
            for i in range(300):
                c.execute(
                    "INSERT INTO events (ts, type, category, severity, payload_json) "
                    "VALUES (?, 'x', 'system', 20, ?)",
                    (float(i), "p" * 200),
                )
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    data = bytearray(path.read_bytes())
    for offset in range(4096 * 2, len(data) - 100, 4096):
        data[offset : offset + 50] = b"\xff" * 50
    path.write_bytes(bytes(data))
    with Database(path) as db:
        assert db.recovered_from is not None
        assert scalar(db, "SELECT COUNT(*) AS n FROM events") == 0


def test_transactions_commit_and_roll_back(tmp_path: Path) -> None:
    with Database(tmp_path / "x.db") as db:
        store = SettingsStore(db)
        with db.transaction() as c:
            c.execute("INSERT INTO settings VALUES ('a', '1', 0)")
        with pytest.raises(RuntimeError):
            failing_write(db)
        assert store.all() == {"a": 1}


def test_a_transaction_cannot_be_nested(tmp_path: Path) -> None:
    with Database(tmp_path / "x.db") as db, db.transaction(), pytest.raises(PersistenceError):
        db.transaction().__enter__()


def test_writers_on_many_threads_do_not_lose_rows(tmp_path: Path) -> None:
    with Database(tmp_path / "x.db") as db:
        errors: list[BaseException] = []

        def work(n: int) -> None:
            try:
                for i in range(25):
                    with db.transaction() as c:
                        c.execute("INSERT INTO settings VALUES (?, '0', 0)", (f"{n}-{i}",))
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert scalar(db, "SELECT COUNT(*) AS n FROM settings") == 200


def test_processes_opening_a_new_database_together_migrate_once(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    results: list[int] = []
    errors: list[BaseException] = []

    def open_it() -> None:
        try:
            with Database(path) as db:
                results.append(db.schema_version)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=open_it) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert results == [latest_version()] * 6
    with Database(path) as db:
        assert scalar(db, "SELECT COUNT(*) AS n FROM schema_migrations") == latest_version()


def test_using_a_closed_database_raises(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.db")
    db.close()
    db.close()
    with pytest.raises(PersistenceError):
        db.fetchall("SELECT 1")


def test_migration_versions_must_be_a_gapless_sequence() -> None:
    check_sequence((V1, V2))
    with pytest.raises(ValueError, match="expected"):
        check_sequence((V1, Migration(3, "three", "SELECT 1;")))
    with pytest.raises(ValueError, match="invalid migration"):
        Migration(0, "zero", "")
    with pytest.raises(ValueError, match="invalid migration"):
        Migration(1, "Bad Name", "")


def test_a_migration_cut_off_mid_statement_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(PersistenceError):
        Database(tmp_path / "x.db", migrations=[Migration(1, "cut", "CREATE TABLE t (id")])


def test_shipped_migrations_are_a_valid_sequence() -> None:
    check_sequence(MIGRATIONS)
    assert latest_version() == len(MIGRATIONS)


def test_settings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "x.db"
    with Database(path) as db:
        store = SettingsStore(db)
        store.set("limits", {"max": 2, "names": ["a", "b"]})
        store.set("limits", {"max": 3})
        assert store.get("limits") == {"max": 3}
        assert store.get("missing", "fallback") == "fallback"
        assert store.delete("limits") is True
        assert store.delete("limits") is False
        store.set("kept", True)
    with Database(path) as db:
        assert SettingsStore(db).all() == {"kept": True}


def test_closing_while_other_threads_work_never_crashes(tmp_path: Path) -> None:
    db = Database(tmp_path / "x.db")
    stop = threading.Event()
    problems: list[BaseException] = []

    def hammer() -> None:
        while not stop.is_set():
            try:
                db.fetchall("SELECT * FROM settings")
                with db.transaction() as c:
                    c.execute("INSERT OR REPLACE INTO settings VALUES ('k', '1', 0)")
            except PersistenceError:
                return  # closed: the right answer
            except BaseException as exc:
                problems.append(exc)
                return

    threads = [threading.Thread(target=hammer) for _ in range(6)]
    for t in threads:
        t.start()
    db.close()
    stop.set()
    for t in threads:
        t.join(10)
    assert not problems
    assert not any(t.is_alive() for t in threads)
