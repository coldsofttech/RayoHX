"""Runs downloads in background threads and keeps their state in memory.

Routes call this; the work itself is done by ``rayohx``. Jobs are lost when the process ends, but
partial downloads resume because the engine keeps its own state on disk.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rayohx import CancellationToken
from rayohx.enums import DownloadState

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

    from rayohx.downloader import Downloader
    from rayohx.events import DownloadEvent

    from rayohx_api.schemas.v1.downloads import DownloadCreate

MAX_JOBS = 200
_BAD_NAME = r'[\\/:*?"<>|\x00-\x1f]'


class UnsafeFilenameError(ValueError):
    """The client asked for a name that could leave the download folder."""


def safe_filename(name: str) -> str:
    import re

    cleaned = name.strip()
    if not cleaned or cleaned in {".", ".."} or re.search(_BAD_NAME, cleaned):
        raise UnsafeFilenameError("Use a plain file name without folders or special characters.")
    return cleaned


@dataclass
class JobRecord:
    id: str
    url: str
    state: DownloadState = DownloadState.QUEUED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    progress: dict[str, Any] | None = None
    output_path: str | None = None
    output_size: int | None = None
    error: str | None = None
    downloader: Downloader | None = None
    token: CancellationToken = field(default_factory=CancellationToken)


class JobManager:
    def __init__(self, directory: Path, max_active: int) -> None:
        import threading
        from collections import OrderedDict

        self.directory = directory
        self._slots = threading.BoundedSemaphore(max_active)
        self._jobs: OrderedDict[str, JobRecord] = OrderedDict()
        self._lock = threading.RLock()

    def list(self) -> list[JobRecord]:
        with self._lock:
            return list(reversed(self._jobs.values()))

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def create(self, request: DownloadCreate, *, concurrency: int) -> JobRecord:
        import threading
        import uuid

        from rayohx._redaction import redact_url
        from rayohx.config import DownloadConfig, NetworkConfig, OutputConfig, SelectionConfig
        from rayohx.downloader import Downloader
        from rayohx.enums import OutputFormat

        filename = safe_filename(request.filename) if request.filename else None
        self.directory.mkdir(parents=True, exist_ok=True)
        config = DownloadConfig(
            concurrency=concurrency,
            network=NetworkConfig(headers=dict(request.network.headers)),
            output=OutputConfig(
                directory=self.directory,
                format=OutputFormat(request.format),
                overwrite=request.overwrite,
            ),
            selection=SelectionConfig(
                quality=request.quality,
                audio_languages=tuple(request.audio),
                subtitle_languages=tuple(request.subtitles),
                video_only=request.video_only,
            ),
        )
        record = JobRecord(id=uuid.uuid4().hex[:12], url=redact_url(request.url))
        output = self.directory / filename if filename else None
        downloader = Downloader(
            request.url,
            output=output,
            config=config,
            cancel=record.token,
            download_id=record.id,
        )
        record.downloader = downloader
        downloader.events.subscribe(lambda event: self._on_event(record, event))
        with self._lock:
            self._jobs[record.id] = record
            self._trim()
        threading.Thread(target=self._run, args=(record,), daemon=True).start()
        return record

    def _trim(self) -> None:
        for key in [k for k, j in self._jobs.items() if j.state.is_terminal]:
            if len(self._jobs) <= MAX_JOBS:
                break
            del self._jobs[key]

    def _on_event(self, record: JobRecord, event: DownloadEvent) -> None:
        from rayohx.serialization import progress_to_dict

        record.state = event.state
        record.updated_at = time.time()
        if event.progress is not None:
            record.progress = progress_to_dict(event.progress)

    def _run(self, record: JobRecord) -> None:
        from rayohx.serialization import progress_to_dict

        assert record.downloader is not None  # noqa: S101
        with self._slots:
            if record.token.is_cancelled:
                record.state = DownloadState.CANCELLED
                record.updated_at = time.time()
                return
            result = record.downloader.run()
        record.state = result.state
        record.progress = progress_to_dict(result.progress)
        record.error = result.error
        if result.output:
            record.output_path = result.output.path.name
            record.output_size = result.output.size_bytes
        record.updated_at = time.time()

    def pause(self, record: JobRecord) -> None:
        if record.downloader:
            record.downloader.pause()

    def resume(self, record: JobRecord) -> None:
        if record.downloader:
            record.downloader.resume()

    def cancel(self, record: JobRecord) -> None:
        record.token.cancel()
        if record.state is DownloadState.QUEUED:
            record.state = DownloadState.CANCELLED
            record.updated_at = time.time()

    def remove(self, record: JobRecord) -> bool:
        """Forget a finished job. Running ones must be cancelled first."""
        if not record.state.is_terminal:
            return False
        with self._lock:
            self._jobs.pop(record.id, None)
        return True
