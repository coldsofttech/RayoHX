import sqlite3
from pathlib import Path

import pytest

import rayohx
from rayohx.platform import Rayo
from rayohx.platform.errors import PersistenceError
from rayohx.platform.events import Severity
from rayohx.platform.persistence import latest_version


def test_rayo_opens_its_folders_and_database(tmp_path: Path) -> None:
    with Rayo(home=tmp_path / "h") as rayo:
        assert rayo.paths.database_path.is_file()
        assert rayo.paths.config_dir.is_dir()
        assert rayo.schema_version == latest_version()
        assert rayo.events.emit("example.hello").id == 1


def test_state_survives_a_restart(tmp_path: Path) -> None:
    with Rayo(home=tmp_path) as rayo:
        rayo.settings.set("max_active", 3)
        rayo.events.emit("a")
    with Rayo(home=tmp_path) as rayo:
        assert rayo.settings.get("max_active") == 3
        assert [e.type for e in rayo.event_store.query()] == ["a"]


def test_environment_selects_the_folders(tmp_path: Path) -> None:
    with Rayo(environ={"RAYOHX_HOME": str(tmp_path / "env")}) as rayo:
        assert rayo.paths.data_dir == tmp_path / "env" / "data"


def test_a_damaged_database_is_replaced_and_the_user_is_told(tmp_path: Path) -> None:
    with Rayo(home=tmp_path) as rayo:
        path = rayo.paths.database_path
    path.write_bytes(b"not a database" * 200)
    with Rayo(home=tmp_path) as rayo:
        (event,) = rayo.event_store.query()
        assert event.type == "system.database_recovered"
        assert event.severity is Severity.WARNING
        assert ".corrupt-" in event.payload["moved_to"]


def test_a_foreign_database_is_refused_not_overwritten(tmp_path: Path) -> None:
    with Rayo(home=tmp_path) as rayo:
        path = rayo.paths.database_path
    path.unlink()
    for suffix in ("-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    foreign = sqlite3.connect(path)
    foreign.execute("CREATE TABLE settings (anything TEXT)")
    foreign.commit()
    foreign.close()
    with pytest.raises(PersistenceError):
        Rayo(home=tmp_path)
    check = sqlite3.connect(path)
    try:
        assert check.execute("SELECT name FROM sqlite_master").fetchall() == [("settings",)]
    finally:
        check.close()


def test_closing_twice_is_fine(tmp_path: Path) -> None:
    rayo = Rayo(home=tmp_path)
    rayo.close()
    rayo.close()


def test_the_top_level_package_exports_rayo() -> None:
    assert rayohx.Rayo is Rayo
