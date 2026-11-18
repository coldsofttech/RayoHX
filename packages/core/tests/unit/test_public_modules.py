"""The public ``rayohx.redaction`` and ``rayohx.storage`` modules front ends rely on."""

import os
import time
from pathlib import Path

import rayohx
from rayohx.enums import DownloadState
from rayohx.events import DownloadStateMachine
from rayohx.redaction import REDACTED, redact_headers, redact_text, redact_url
from rayohx.storage import (
    clean_workspaces,
    find_workspaces,
    folder_size,
    inspect_workspace,
    is_workspace_in_use,
)


def make_workspace(parent: Path, name: str, *, size: int = 10, age_days: float = 0) -> Path:
    folder = parent / name
    (folder / "segments").mkdir(parents=True)
    (folder / "state.json").write_text("{}", encoding="utf-8")
    (folder / "segments" / "0.part").write_bytes(b"x" * size)
    if age_days:
        stamp = time.time() - age_days * 86400
        os.utime(folder / "state.json", (stamp, stamp))
    return folder


def test_redaction_is_public() -> None:
    assert (
        redact_url("https://u:p@h.test/a?token=abc")
        == f"https://{REDACTED}@h.test/a?token={REDACTED}"
    )
    assert redact_headers({"Authorization": "x", "Accept": "y"}) == {
        "Authorization": REDACTED,
        "Accept": "y",
    }
    assert "secret" not in redact_text("password=secret")


def test_workspaces_are_found_by_name_or_by_key_with_state(tmp_path: Path) -> None:
    named = make_workspace(tmp_path, ".rayohx-abc")
    keyed = make_workspace(tmp_path, "0123456789abcdef")
    (tmp_path / "0123456789abcde0").mkdir()  # key-shaped but no state: not ours
    (tmp_path / "movie.mp4").write_bytes(b"data")
    assert find_workspaces(tmp_path) == sorted([named, keyed])


def test_missing_folder_has_no_workspaces(tmp_path: Path) -> None:
    assert find_workspaces(tmp_path / "nope") == []


def test_symlinked_workspaces_are_ignored(tmp_path: Path) -> None:
    real = make_workspace(tmp_path / "elsewhere", ".rayohx-real")
    (tmp_path / ".rayohx-link").symlink_to(real, target_is_directory=True)
    assert find_workspaces(tmp_path) == []


def test_inspect_reports_size_age_and_lock(tmp_path: Path) -> None:
    folder = make_workspace(tmp_path, ".rayohx-a", size=100, age_days=3)
    info = inspect_workspace(folder)
    assert info.size_bytes == folder_size(folder) == 102
    assert 2.9 < info.age_days < 3.1
    assert not info.in_use
    assert info.safe_to_remove
    assert info.name == ".rayohx-a"


def test_a_held_lock_marks_the_workspace_in_use(tmp_path: Path) -> None:
    from rayohx._download._workspace import Workspace

    folder = tmp_path / ".rayohx-busy"
    with Workspace(folder):
        assert is_workspace_in_use(folder)
        assert not inspect_workspace(folder).safe_to_remove
    assert not is_workspace_in_use(folder)


def test_clean_respects_age_dry_run_and_locks(tmp_path: Path) -> None:
    from rayohx._download._workspace import Workspace

    old = make_workspace(tmp_path, ".rayohx-old", age_days=5)
    fresh = make_workspace(tmp_path, ".rayohx-new")
    busy = make_workspace(tmp_path, ".rayohx-busy", age_days=9)
    output = tmp_path / "movie.mp4"
    output.write_bytes(b"keep me")

    with Workspace(busy):
        removed, skipped = clean_workspaces(tmp_path, older_than_days=1, dry_run=True)
        assert [i.name for i in removed] == [".rayohx-old"]
        assert skipped == 1
        assert old.exists()

        removed, skipped = clean_workspaces(tmp_path, older_than_days=1)
        assert [i.name for i in removed] == [".rayohx-old"]
        assert not old.exists()
        assert fresh.exists()
        assert busy.exists()
    assert output.read_bytes() == b"keep me"


def test_verifying_sits_between_finalizing_and_completed() -> None:
    machine = DownloadStateMachine(DownloadState.FINALIZING)
    assert machine.can_move_to(DownloadState.VERIFYING)
    assert machine.can_move_to(DownloadState.COMPLETED)  # the engine does not verify yet
    machine.move_to(DownloadState.VERIFYING)
    assert machine.can_move_to(DownloadState.COMPLETED)
    assert machine.can_move_to(DownloadState.FAILED)
    assert not machine.can_move_to(DownloadState.DOWNLOADING)
    assert not DownloadState.VERIFYING.is_terminal


def test_rayo_is_a_lazy_export() -> None:
    assert "Rayo" in dir(rayohx)
    assert rayohx.Rayo.__module__ == "rayohx.platform.facade"
