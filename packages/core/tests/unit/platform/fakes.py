"""A scripted stand-in for ``Downloader`` so queue tests run in milliseconds."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from rayohx.cancellation import CancellationToken
from rayohx.enums import ContainerFormat, DownloadState, EventType
from rayohx.errors import NetworkConnectionError, RayoHXError
from rayohx.events import DownloadEvent, EventBus
from rayohx.models import DownloadProgress, DownloadResult, OutputInfo

Script = Callable[["FakeDownloader"], DownloadResult]


class FakeDownloader:
    """Behaves like ``Downloader``; what ``run`` does is decided by a script per address."""

    scripts: ClassVar[dict[str, Script]] = {}
    started: ClassVar[list[str]] = []
    started_lock = threading.Lock()

    def __init__(
        self,
        url: str,
        *,
        output: Path | None = None,
        config: Any = None,
        cancel: CancellationToken | None = None,
        download_id: str | None = None,
        playlist_text: str | None = None,
        **_: Any,
    ) -> None:
        self.url = url
        self.output = output
        self.config = config
        self.token = cancel or CancellationToken()
        self.download_id = download_id or "x"
        self.events = EventBus()
        self.exception: Exception | None = None

    def emit(self, kind: EventType, state: DownloadState, **kw: Any) -> None:
        kw.setdefault("progress", DownloadProgress(state=state))
        self.events.emit(DownloadEvent(type=kind, download_id=self.download_id, state=state, **kw))

    def result(self, state: DownloadState, *, error: str | None = None) -> DownloadResult:
        out = None
        if state is DownloadState.COMPLETED:
            path = self.output or Path(self.config.output.directory) / "fake.ts"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"data")
            out = OutputInfo(path=path, container=ContainerFormat.MPEG_TS, size_bytes=4)
        return DownloadResult(
            download_id=self.download_id,
            url=self.url,
            state=state,
            elapsed_seconds=0.0,
            progress=DownloadProgress(state=state),
            output=out,
            error=error,
        )

    def run(self) -> DownloadResult:
        with self.started_lock:
            self.started.append(self.url)
        script = self.scripts.get(self.url) or self.scripts.get("*") or ok
        return script(self)


def ok(d: FakeDownloader) -> DownloadResult:
    d.emit(EventType.DOWNLOAD_STARTED, DownloadState.INSPECTING)
    d.emit(EventType.STREAM_SELECTED, DownloadState.PREPARING)
    d.emit(EventType.DOWNLOAD_PROGRESS, DownloadState.DOWNLOADING)
    return d.result(DownloadState.COMPLETED)


def fail_with(exc: Exception) -> Script:
    def run(d: FakeDownloader) -> DownloadResult:
        d.emit(EventType.DOWNLOAD_STARTED, DownloadState.INSPECTING)
        d.exception = exc
        message = exc.describe() if isinstance(exc, RayoHXError) else str(exc)
        return d.result(DownloadState.FAILED, error=message)

    return run


def flaky(times: int, final: Script = ok) -> Script:
    """Fail with a retryable network error ``times`` times, then do ``final``."""
    count = {"n": 0}

    def run(d: FakeDownloader) -> DownloadResult:
        count["n"] += 1
        if count["n"] <= times:
            return fail_with(NetworkConnectionError("connection reset"))(d)
        return final(d)

    return run


def block_until_stopped(gate: threading.Event | None = None) -> Script:
    """Download "forever": report DOWNLOADING and wait until cancelled (or ``gate`` opens)."""

    def run(d: FakeDownloader) -> DownloadResult:
        d.emit(EventType.DOWNLOAD_STARTED, DownloadState.INSPECTING)
        d.emit(EventType.DOWNLOAD_PROGRESS, DownloadState.DOWNLOADING)
        while not d.token.wait(0.01):
            if gate is not None and gate.is_set():
                return d.result(DownloadState.COMPLETED)
        return d.result(DownloadState.CANCELLED)

    return run


def reset() -> None:
    FakeDownloader.scripts = {}
    FakeDownloader.started = []
