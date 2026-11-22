from collections.abc import Iterator
from pathlib import Path

import pytest
from rayohx.enums import DownloadState

from rayohx_api.jobs import JobManager, JobRecord
from rayohx_api.store import INTERRUPTED, Store


@pytest.fixture(autouse=True)
def _close_stores(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Close every store a test opens so SQLite connections don't leak."""
    opened: list[Store] = []

    original = Store.__init__

    def tracked(self: Store, path: Path) -> None:
        original(self, path)
        opened.append(self)

    monkeypatch.setattr(Store, "__init__", tracked)
    yield
    for opened_store in opened:
        opened_store.close()


def test_jobs_survive_restart_and_unfinished_ones_are_interrupted(tmp_path: Path) -> None:
    db = tmp_path / "h.db"
    store = Store(db)
    store.save(JobRecord(id="a", url="u", state=DownloadState.COMPLETED, progress={"x": 1}))
    store.save(JobRecord(id="b", url="u", state=DownloadState.DOWNLOADING))

    manager = JobManager(tmp_path, max_active=1, store=Store(db))

    done, cut = manager.get("a"), manager.get("b")
    assert done
    assert done.progress == {"x": 1}
    assert cut
    assert cut.state is DownloadState.FAILED
    assert cut.error == INTERRUPTED


def test_clear_removes_finished_jobs_from_memory_and_disk(tmp_path: Path) -> None:
    db = tmp_path / "h.db"
    manager = JobManager(tmp_path, max_active=1, store=Store(db))
    record = JobRecord(id="a", url="u", state=DownloadState.COMPLETED)
    manager._jobs["a"] = record
    manager._save(record)

    assert manager.clear() == 1
    assert JobManager(tmp_path, max_active=1, store=Store(db)).all() == []


def test_concurrency_default_is_saved(tmp_path: Path) -> None:
    from rayohx_api.routers.v1.deps import Preferences

    db = tmp_path / "h.db"
    Preferences(tmp_path, Store(db)).update({"concurrency": 8})

    assert Preferences(tmp_path, Store(db)).concurrency == 8
