"""Finding and removing leftover working folders."""

import os
import time
from pathlib import Path

import pytest

from rayohx import LeftoverWorkspace, find_workspaces, remove_workspaces


def make(parent: Path, name: str = ".rayohx-0123456789abcdef", age_days: float = 0) -> Path:
    folder = parent / name
    (folder / "segments").mkdir(parents=True)
    (folder / "state.json").write_text("{}", encoding="utf-8")
    (folder / "segments" / "000001").write_bytes(b"x" * 2048)
    if age_days:
        stamp = time.time() - age_days * 86400
        os.utime(folder / "state.json", (stamp, stamp))
    return folder


def test_finds_named_folders_and_reports_size_and_age(tmp_path: Path) -> None:
    folder = make(tmp_path, age_days=2)
    (tmp_path / "movie.mp4").write_bytes(b"data")
    (tmp_path / "other").mkdir()
    [found] = find_workspaces([tmp_path])
    assert found.path == folder
    assert found.size >= 2048
    assert 1.9 < found.age_days < 2.1
    assert not found.in_use


def test_finds_hash_named_folders_only_with_a_state_file(tmp_path: Path) -> None:
    keyed = make(tmp_path, "0123456789abcdef")
    (tmp_path / "fedcba9876543210").mkdir()
    assert [w.path for w in find_workspaces([tmp_path])] == [keyed]


def test_older_than_days_keeps_recent_folders(tmp_path: Path) -> None:
    make(tmp_path, ".rayohx-aaaaaaaaaaaaaaaa", age_days=0)
    old = make(tmp_path, ".rayohx-bbbbbbbbbbbbbbbb", age_days=5)
    assert [w.path for w in find_workspaces([tmp_path], older_than_days=3)] == [old]


def test_defaults_to_the_current_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = make(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert [w.path.name for w in find_workspaces()] == [folder.name]


def test_a_missing_folder_is_skipped(tmp_path: Path) -> None:
    assert find_workspaces([tmp_path / "missing"]) == []


def test_symlinked_folders_are_ignored(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    target = make(real)
    link = tmp_path / ".rayohx-linklinklinklink"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available")
    assert [w.path for w in find_workspaces([tmp_path])] == []
    assert [w.path for w in find_workspaces([real])] == [target]


def test_remove_deletes_folders_and_skips_those_in_use(tmp_path: Path) -> None:
    gone = make(tmp_path, ".rayohx-aaaaaaaaaaaaaaaa")
    busy = make(tmp_path, ".rayohx-bbbbbbbbbbbbbbbb")
    workspaces = [LeftoverWorkspace(gone, 1, 0, False), LeftoverWorkspace(busy, 1, 0, True)]
    assert remove_workspaces(workspaces) == [gone]
    assert not gone.exists()
    assert busy.exists()


@pytest.mark.skipif(os.name == "nt", reason="uses a POSIX file lock")
def test_a_folder_a_download_holds_is_in_use(tmp_path: Path) -> None:
    from rayohx._download._workspace import _FileLock

    busy = make(tmp_path)
    lock = _FileLock(busy / "lock")
    assert lock.acquire()
    try:
        [found] = find_workspaces([tmp_path])
    finally:
        lock.release()
    assert found.in_use
