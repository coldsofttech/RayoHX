from typing import Any

import pytest
from pydantic import ValidationError

from rayohx_api.schemas.v1 import DownloadCreate, Job, JobList, Progress

URL = "https://example.test/master.m3u8"


def test_download_create_defaults() -> None:
    assert DownloadCreate(url=URL).model_dump() == {
        "url": URL,
        "filename": None,
        "quality": "best",
        "audio": [],
        "subtitles": [],
        "video_only": False,
        "format": "auto",
        "overwrite": False,
        "network": {"headers": {}},
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"url": ""},
        {"url": "u" * 4097},
        {"filename": "f" * 201},
        {"audio": ["x"] * 17},
        {"subtitles": ["x"] * 17},
        {"format": "avi"},
    ],
)
def test_download_create_rejects_invalid(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        DownloadCreate(**{"url": URL, **overrides})


def test_download_create_accepts_limits() -> None:
    request = DownloadCreate(
        url="u" * 4096, filename="f" * 200, audio=["en"] * 16, format="mkv", video_only=True
    )
    assert request.format == "mkv"
    assert len(request.audio) == 16


def test_download_create_list_defaults_are_independent() -> None:
    first, second = DownloadCreate(url=URL), DownloadCreate(url=URL)
    first.audio.append("en")
    assert second.audio == []


def test_progress_defaults_and_required_state() -> None:
    progress = Progress(state="downloading")
    assert progress.downloaded_bytes == 0
    assert progress.total_bytes is None
    assert progress.speed == 0.0
    with pytest.raises(ValidationError):
        Progress()  # type: ignore[call-arg]


def test_job_minimal_and_full() -> None:
    job = Job(id="a", url=URL, state="queued", created_at=1.0, updated_at=2.0)
    assert job.progress is None
    assert job.output_path is None
    full = Job(
        id="a",
        url=URL,
        state="completed",
        created_at=1.0,
        updated_at=2.0,
        progress={"state": "completed", "fraction": 1.0},  # type: ignore[arg-type]
        output_path="a.mp4",
        output_size_bytes=7,
    )
    assert isinstance(full.progress, Progress)
    assert full.progress.fraction == 1.0


@pytest.mark.parametrize("missing", ["id", "url", "state", "created_at", "updated_at"])
def test_job_requires_fields(missing: str) -> None:
    data: dict[str, Any] = {
        "id": "a",
        "url": URL,
        "state": "queued",
        "created_at": 1.0,
        "updated_at": 2.0,
    }
    del data[missing]
    with pytest.raises(ValidationError):
        Job(**data)


def test_job_list_holds_jobs() -> None:
    data = {"id": "a", "url": URL, "state": "queued", "created_at": 1, "updated_at": 2}
    assert JobList(items=[data]).items[0].id == "a"  # type: ignore[list-item]
    assert JobList(items=[]).items == []
