"""Storage: the policy, the guard, auto-pause and resume, accounting and safe cleanup."""

import os
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from rayohx.errors import ConfigurationError
from rayohx.platform import Rayo
from rayohx.platform.jobs import JobState
from rayohx.platform.storage import (
    StorageGuard,
    StorageLevel,
    StoragePolicy,
    format_size,
    parse_size,
    remaining_need,
)
from tests.unit.platform import fakes
from tests.unit.platform.conftest import state_of, wait_state

MB = 1_000_000
URL = "https://media.test/{}/master.m3u8"


class Disk:
    """A pretend disk whose free space a test sets."""

    def __init__(self, free: int) -> None:
        self.free = free

    def __call__(self, _: Path) -> int:
        return self.free


# --- sizes and policy --------------------------------------------------------------------


def test_sizes_are_parsed_and_shown() -> None:
    assert parse_size("5GB") == 5 * 1024**3
    assert parse_size("1.5 MiB") == 1_572_864
    assert parse_size(300) == 300
    assert format_size(5 * 1024**3) == "5.0 GiB"
    with pytest.raises(ConfigurationError):
        parse_size("lots")


def test_thresholds_must_be_in_order() -> None:
    StoragePolicy(warn_below=10, pause_below=5, stop_below=1)
    with pytest.raises(ConfigurationError, match="out of order"):
        StoragePolicy(warn_below=1, pause_below=5)
    with pytest.raises(ConfigurationError):
        StoragePolicy(stop_below=-1)


def test_levels_have_hysteresis() -> None:
    policy = StoragePolicy(warn_below=1000, pause_below=500, stop_below=100, resume_margin=0.2)
    assert policy.level_for(2000) is StorageLevel.OK
    assert policy.level_for(900) is StorageLevel.LOW
    assert policy.level_for(400) is StorageLevel.PAUSE
    assert policy.level_for(50) is StorageLevel.STOP
    # Just over the pause line is not enough to leave it; a margin of room is.
    assert policy.level_for(520, current=StorageLevel.PAUSE) is StorageLevel.PAUSE
    assert policy.level_for(700, current=StorageLevel.PAUSE) is StorageLevel.LOW


def test_the_policy_is_saved(rayo: Rayo) -> None:
    assert not rayo.storage.policy().active
    rayo.storage.set_policy(StoragePolicy(warn_below=5 * MB, pause_below=2 * MB))
    assert rayo.storage.policy().pause_below == 2 * MB


# --- the guard ---------------------------------------------------------------------------


def test_remaining_need_comes_from_progress() -> None:
    assert remaining_need(None) == 0
    assert remaining_need({"total_bytes": None}) == 0
    assert remaining_need({"total_bytes": 1000, "written_bytes": 400}) == 650
    assert remaining_need({"total_bytes": 1000, "written_bytes": 5000}) == 0


def test_admission_counts_what_running_jobs_still_need() -> None:
    disk = Disk(1000)
    policy = StoragePolicy(pause_below=200)
    guard = StorageGuard(lambda: policy, lambda: Path("."), free=disk)
    assert guard.admit(500, {})
    running = {"a": {"total_bytes": 600, "written_bytes": 0}}  # still needs 630
    assert not guard.admit(500, running)  # 1000 - 630 - 500 < 200
    assert guard.admit(100, running)


def test_a_failing_disk_read_never_blocks() -> None:
    def broken(_: Path) -> int:
        raise OSError("gone")

    guard = StorageGuard(lambda: StoragePolicy(pause_below=1), lambda: Path("."), free=broken)
    assert guard.admit(10**12, {})
    assert guard.review({"a": None}).level is StorageLevel.OK


# --- the runner reacts -------------------------------------------------------------------


def test_low_space_pauses_running_jobs_and_they_resume_by_themselves(
    make_rayo: Callable[..., Rayo],
) -> None:
    disk = Disk(100 * MB)
    rayo = make_rayo(free_space=disk, storage_interval=0.0)
    rayo.storage.set_policy(StoragePolicy(warn_below=50 * MB, pause_below=20 * MB))
    fakes.FakeDownloader.scripts["*"] = fakes.block_until_stopped()
    job = rayo.queue.add(URL.format("a"))
    rayo.queue.start()
    wait_state(rayo, job.id, JobState.DOWNLOADING)

    disk.free = 10 * MB
    wait_state(rayo, job.id, JobState.PAUSED)
    paused = rayo.queue.get(job.id)
    assert paused is not None
    assert paused.auto_paused

    disk.free = 100 * MB
    wait_state(rayo, job.id, JobState.DOWNLOADING)
    resumed = rayo.queue.get(job.id)
    assert resumed is not None
    assert not resumed.auto_paused
    kinds = {e.type for e in rayo.event_store.query(limit=500)}
    assert {"storage.paused", "storage.recovered"} <= kinds


def test_a_user_pause_is_not_resumed_by_the_guard(make_rayo: Callable[..., Rayo]) -> None:
    disk = Disk(100 * MB)
    rayo = make_rayo(free_space=disk, storage_interval=0.0)
    rayo.storage.set_policy(StoragePolicy(pause_below=20 * MB))
    fakes.FakeDownloader.scripts["*"] = fakes.block_until_stopped()
    job = rayo.queue.add(URL.format("a"))
    rayo.queue.start()
    wait_state(rayo, job.id, JobState.DOWNLOADING)
    rayo.queue.pause(job.id)
    wait_state(rayo, job.id, JobState.PAUSED)
    disk.free = 5 * MB
    time.sleep(0.2)
    disk.free = 100 * MB
    time.sleep(0.3)
    assert state_of(rayo, job.id) is JobState.PAUSED


def test_a_nearly_full_disk_stops_jobs_with_a_clear_code(make_rayo: Callable[..., Rayo]) -> None:
    disk = Disk(100 * MB)
    rayo = make_rayo(free_space=disk, storage_interval=0.0)
    rayo.storage.set_policy(StoragePolicy(pause_below=20 * MB, stop_below=5 * MB))
    fakes.FakeDownloader.scripts["*"] = fakes.block_until_stopped()
    job = rayo.queue.add(URL.format("a"))
    rayo.queue.start()
    wait_state(rayo, job.id, JobState.DOWNLOADING)
    disk.free = MB
    wait_state(rayo, job.id, JobState.FAILED)
    failed = rayo.queue.get(job.id)
    assert failed is not None
    assert failed.error_code == "STORAGE_LOW"


def test_a_job_that_would_not_fit_waits_in_the_queue(make_rayo: Callable[..., Rayo]) -> None:
    disk = Disk(10 * MB)
    rayo = make_rayo(free_space=disk, storage_interval=0.0)
    rayo.storage.set_policy(StoragePolicy(pause_below=20 * MB))
    job = rayo.queue.add(URL.format("a"))
    rayo.queue.start()
    time.sleep(0.3)
    assert state_of(rayo, job.id) is JobState.QUEUED
    disk.free = 500 * MB
    wait_state(rayo, job.id, JobState.COMPLETED)


# --- accounting and cleanup --------------------------------------------------------------


def test_the_snapshot_reports_use_and_policy(rayo: Rayo) -> None:
    snapshot = rayo.storage.snapshot().to_dict()
    assert snapshot["level"] == "ok"
    assert {v["role"] for v in snapshot["volumes"]} >= {"downloads"}
    assert snapshot["reserved_bytes"] == 0


def make_workspace(root: Path, name: str, size: int = 2000, age_days: float = 30) -> Path:
    folder = root / f".rayohx-{name}"
    folder.mkdir(parents=True)
    (folder / "state.json").write_text("{}")
    (folder / "seg.part").write_bytes(b"x" * size)
    old = time.time() - age_days * 86400
    for item in (folder / "state.json", folder / "seg.part", folder):
        os.utime(item, (old, old))
    return folder


def test_cleanup_only_lists_unless_told_and_never_touches_output(rayo: Rayo) -> None:
    out = rayo.download_dir
    out.mkdir(parents=True, exist_ok=True)
    finished = out / "movie.mp4"
    finished.write_bytes(b"precious")
    stale = make_workspace(out, "stale")
    result = rayo.storage.cleanup(dry_run=True, older_than_days=7)
    assert stale.exists()
    assert [i.name for i in result.plan.items] == [stale.name]
    assert result.removed == ()

    applied = rayo.storage.cleanup(dry_run=False, older_than_days=7)
    assert not stale.exists()
    assert applied.freed_bytes > 0
    assert finished.read_bytes() == b"precious"


def test_recent_workspaces_are_kept(rayo: Rayo) -> None:
    out = rayo.download_dir
    out.mkdir(parents=True, exist_ok=True)
    fresh = make_workspace(out, "fresh", age_days=0)
    result = rayo.storage.cleanup(dry_run=False, older_than_days=7)
    assert fresh.exists()
    assert any("newer than the limit" in line for line in result.plan.kept)


def test_a_workspace_of_a_resumable_job_is_kept(rayo: Rayo) -> None:
    out = rayo.download_dir
    out.mkdir(parents=True, exist_ok=True)
    folder = make_workspace(out, "owned")
    job = rayo.queue.add(URL.format("a"))
    rayo.queue.pause(job.id)
    rayo.jobs.add_workspace(job.id, str(folder))
    found = {w.name: w for w in rayo.storage.workspaces()}[folder.name]
    assert not found.safe_to_remove
    assert found.job_id == job.id
    rayo.storage.cleanup(dry_run=False, older_than_days=0)
    assert folder.exists()
