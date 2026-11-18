"""Runs downloads in background threads and keeps their state in memory.

Routes call this; the work itself is done by ``rayohx``. Jobs are lost when the process ends, but
partial downloads resume because the engine keeps its own state on disk.
"""

import re
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any

from rayohx import CancellationToken
from rayohx._redaction import redact_url
from rayohx.downloader import Downloader
from rayohx.downloader.batch import batch_outputs
from rayohx.enums import DownloadState
from rayohx.errors import ConfigurationError
from rayohx.events import DownloadEvent
from rayohx.serialization import progress_to_dict

from rayohx_api.build import download_config, sources
from rayohx_api.schemas_v1 import DownloadCreate

MAX_JOBS = 200
_BAD_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class UnsafeFilenameError(ValueError):
    """The client asked for a name that could leave the download folder."""


def safe_filename(name: str) -> str:
    cleaned = name.strip()
    if not cleaned or cleaned in {".", ".."} or _BAD_NAME.search(cleaned):
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
        self.directory = directory
        self._slots = threading.BoundedSemaphore(max_active)
        self._jobs: OrderedDict[str, JobRecord] = OrderedDict()
        self._lock = threading.RLock()

    def all(self) -> list[JobRecord]:
        with self._lock:
            return list(reversed(self._jobs.values()))

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def create(
        self, request: DownloadCreate, *, concurrency: int, local_paths: bool
    ) -> list[JobRecord]:
        """Start one job for each address in the request."""
        urls = sources(request)
        if request.filename and len(urls) > 1:
            raise ConfigurationError("A file name can only be given for a single download.")
        filename = safe_filename(request.filename) if request.filename else None
        self.directory.mkdir(parents=True, exist_ok=True)
        config = download_config(
            request, base=self.directory, local=local_paths, concurrency=concurrency
        )
        folder = config.output.directory or self.directory
        folder.mkdir(parents=True, exist_ok=True)
        if filename:
            outputs: list[Path | None] = [folder / filename]
        elif len(urls) > 1:
            outputs = list(batch_outputs(urls, folder))
        else:
            outputs = [None]
        records = []
        for url, output in zip(urls, outputs, strict=True):
            record = JobRecord(id=uuid.uuid4().hex[:12], url=redact_url(url))
            downloader = Downloader(
                url,
                output=output,
                config=config,
                cancel=record.token,
                download_id=record.id,
                playlist_text=request.playlist_text,
            )
            record.downloader = downloader
            downloader.events.subscribe(partial(self._on_event, record))
            records.append(record)
        with self._lock:
            for record in records:
                self._jobs[record.id] = record
            self._trim()
        for record in records:
            threading.Thread(target=self._run, args=(record,), daemon=True).start()
        return records

    def _trim(self) -> None:
        for key in [k for k, j in self._jobs.items() if j.state.is_terminal]:
            if len(self._jobs) <= MAX_JOBS:
                break
            del self._jobs[key]

    def _on_event(self, record: JobRecord, event: DownloadEvent) -> None:
        record.state = event.state
        record.updated_at = time.time()
        if event.progress is not None:
            record.progress = progress_to_dict(event.progress)

    def _run(self, record: JobRecord) -> None:
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
