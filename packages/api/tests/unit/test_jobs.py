from pathlib import Path
from types import SimpleNamespace

import pytest
from rayohx.enums import DownloadState

from rayohx_api import jobs
from rayohx_api.jobs import JobManager, JobRecord, UnsafeFilenameError, safe_filename


@pytest.mark.parametrize("name", ["", "  ", ".", "..", "a/b.mp4", "a\b.mp4", "a:b", "a\x00b"])
def test_unsafe_filenames_are_rejected(name: str) -> None:
    with pytest.raises(UnsafeFilenameError):
        safe_filename(name)


def test_plain_filename_is_trimmed() -> None:
    assert safe_filename("  movie.mp4 ") == "movie.mp4"


def test_remove_only_finished_jobs(tmp_path: Path) -> None:
    manager = JobManager(tmp_path, max_active=1)
    running = JobRecord(id="a", url="u", state=DownloadState.DOWNLOADING)
    done = JobRecord(id="b", url="u", state=DownloadState.COMPLETED)
    manager._jobs.update({"a": running, "b": done})
    assert manager.remove(running) is False
    assert manager.remove(done) is True
    assert manager.get("b") is None
    assert [j.id for j in manager.list()] == ["a"]


def test_cancel_queued_job_is_cancelled_at_once(tmp_path: Path) -> None:
    manager = JobManager(tmp_path, max_active=1)
    record = JobRecord(id="a", url="u")
    manager.cancel(record)
    assert record.token.is_cancelled
    assert record.state is DownloadState.CANCELLED


def test_cancelled_before_start_never_runs(tmp_path: Path) -> None:
    manager = JobManager(tmp_path, max_active=1)
    record = JobRecord(id="a", url="u", downloader=SimpleNamespace())  # type: ignore[arg-type]
    record.token.cancel()
    manager._run(record)
    assert record.state is DownloadState.CANCELLED


def test_trim_drops_oldest_finished_jobs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs, "MAX_JOBS", 2)
    manager = JobManager(tmp_path, max_active=1)
    for i in range(4):
        manager._jobs[str(i)] = JobRecord(id=str(i), url="u", state=DownloadState.COMPLETED)
    manager._jobs["live"] = JobRecord(id="live", url="u", state=DownloadState.DOWNLOADING)
    manager._trim()
    assert len(manager._jobs) == 2
    assert "live" in manager._jobs


def test_run_records_output(tmp_path: Path) -> None:
    from rayohx.models import DownloadProgress

    result = SimpleNamespace(
        state=DownloadState.COMPLETED,
        progress=DownloadProgress(),
        error=None,
        output=SimpleNamespace(path=tmp_path / "a.mp4", size_bytes=7),
    )
    record = JobRecord(id="a", url="u", downloader=SimpleNamespace(run=lambda: result))  # type: ignore[arg-type]
    JobManager(tmp_path, max_active=1)._run(record)
    assert (record.state, record.output_path, record.output_size) == (
        DownloadState.COMPLETED,
        "a.mp4",
        7,
    )


def test_list_is_newest_first_and_get_finds_by_id(tmp_path: Path) -> None:
    manager = JobManager(tmp_path, max_active=1)
    for name in ("a", "b", "c"):
        manager._jobs[name] = JobRecord(id=name, url="u")
    assert [j.id for j in manager.list()] == ["c", "b", "a"]
    assert manager.get("b") is manager._jobs["b"]
    assert manager.get("missing") is None


def test_cancel_running_job_only_sets_token(tmp_path: Path) -> None:
    manager = JobManager(tmp_path, max_active=1)
    record = JobRecord(id="a", url="u", state=DownloadState.DOWNLOADING)
    manager.cancel(record)
    assert record.token.is_cancelled
    assert record.state is DownloadState.DOWNLOADING


def test_pause_and_resume_delegate_to_downloader(tmp_path: Path) -> None:
    calls: list[str] = []
    downloader = SimpleNamespace(
        pause=lambda: calls.append("pause"), resume=lambda: calls.append("resume")
    )
    manager = JobManager(tmp_path, max_active=1)
    record = JobRecord(id="a", url="u", downloader=downloader)  # type: ignore[arg-type]
    manager.pause(record)
    manager.resume(record)
    assert calls == ["pause", "resume"]


def test_pause_and_resume_without_downloader_do_nothing(tmp_path: Path) -> None:
    manager = JobManager(tmp_path, max_active=1)
    record = JobRecord(id="a", url="u")
    manager.pause(record)
    manager.resume(record)


def test_run_records_failure(tmp_path: Path) -> None:
    from rayohx.models import DownloadProgress

    result = SimpleNamespace(
        state=DownloadState.FAILED, progress=DownloadProgress(), error="boom", output=None
    )
    record = JobRecord(id="a", url="u", downloader=SimpleNamespace(run=lambda: result))  # type: ignore[arg-type]
    JobManager(tmp_path, max_active=1)._run(record)
    assert record.state is DownloadState.FAILED
    assert record.error == "boom"
    assert record.output_path is None


def test_on_event_updates_state_and_progress(tmp_path: Path) -> None:
    from rayohx.models import DownloadProgress

    record = JobRecord(id="a", url="u")
    event = SimpleNamespace(state=DownloadState.DOWNLOADING, progress=DownloadProgress())
    JobManager(tmp_path, max_active=1)._on_event(record, event)  # type: ignore[arg-type]
    assert record.state is DownloadState.DOWNLOADING
    assert record.progress is not None


def test_on_event_without_progress_keeps_previous(tmp_path: Path) -> None:
    record = JobRecord(id="a", url="u", progress={"x": 1})
    event = SimpleNamespace(state=DownloadState.PAUSED, progress=None)
    JobManager(tmp_path, max_active=1)._on_event(record, event)  # type: ignore[arg-type]
    assert record.progress == {"x": 1}


def test_create_rejects_unsafe_filename_before_starting(tmp_path: Path) -> None:
    manager = JobManager(tmp_path / "dl", max_active=1)
    request = SimpleNamespace(filename="../evil.mp4")
    with pytest.raises(UnsafeFilenameError):
        manager.create(request, concurrency=1)  # type: ignore[arg-type]
    assert manager.list() == []
    assert not (tmp_path / "dl").exists()
