"""The download controller: one object that takes a web address to a finished file.

It walks a download through its states (inspecting, preparing, downloading, finalizing), reports
each step as an event, and returns a structured result. A cancelled download ends as
``CANCELLED``, not as a failure. The command line, the API and the window all use this class.
"""

from __future__ import annotations

import dataclasses
import logging
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from rayohx._download._media import MediaDownload
from rayohx._download._output import plan_output
from rayohx._download._sinks import DirectorySink, FileSink
from rayohx._http import HttpClient
from rayohx._logs import set_download_id
from rayohx._redaction import redact_text, redact_url
from rayohx.cancellation import CancellationToken
from rayohx.config import DownloadConfig, validate_url
from rayohx.downloader._result import join_message, output_info
from rayohx.downloader._stream import (
    describe,
    kind,
    load_media,
    probe_container,
    require_single_stream,
)
from rayohx.enums import ContainerFormat, DownloadState, EventType
from rayohx.errors import CancellationError, DownloadError, RayoHXError
from rayohx.events import DownloadEvent, DownloadStateMachine, EventBus
from rayohx.models import DownloadProgress, DownloadResult, MasterPlaylist, OutputInfo
from rayohx.playlist import inspect_playlist
from rayohx.stream import select_stream

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx

    from rayohx._download._sinks import OutputSink
    from rayohx.stream import StreamSelection

logger = logging.getLogger(__name__)


class Downloader:
    """Downloads one stream. Create it, optionally subscribe to ``events``, then call ``run``.

    A ``Downloader`` runs once. Call ``cancel`` from any thread to stop it; ``run`` then returns a
    result in the ``CANCELLED`` state.
    """

    def __init__(
        self,
        url: str,
        *,
        output: Path | str | None = None,
        config: DownloadConfig | None = None,
        events: EventBus | None = None,
        cancel: CancellationToken | None = None,
        download_id: str | None = None,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = validate_url(url)
        self._config = config or DownloadConfig()
        self._output = Path(output) if output is not None else self._config.output.path
        self._bus = events if events is not None else EventBus()
        self._token = cancel if cancel is not None else CancellationToken()
        self._id = download_id or uuid.uuid4().hex[:12]
        self._transport = transport
        self._clock = clock
        self._machine = DownloadStateMachine()
        self._progress = DownloadProgress()
        self._ran = False
        #: The error that ended the download, if it failed.
        self.exception: Exception | None = None
        self._bus.subscribe(self._remember_progress)

    @property
    def download_id(self) -> str:
        """The identifier events and log lines carry."""
        return self._id

    @property
    def state(self) -> DownloadState:
        """Where the download is now."""
        return self._machine.state

    @property
    def events(self) -> EventBus:
        """Subscribe here to follow the download."""
        return self._bus

    def cancel(self) -> None:
        """Ask the download to stop. Safe to call from any thread, and more than once."""
        self._token.cancel()

    # --- running ---------------------------------------------------------------------------

    def run(self) -> DownloadResult:
        """Run the download and return how it ended.

        Completed and cancelled downloads return a result. A failure returns a result in the
        ``FAILED`` state with the message; the original exception is in ``exception``.
        """
        if self._ran:
            raise DownloadError("This download has already run; create a new Downloader.")
        self._ran = True
        set_download_id(self._id)
        started = self._clock()
        try:
            output, final = self._execute()
        except CancellationError:
            return self._end(
                DownloadState.CANCELLED, started, message="The download was cancelled."
            )
        except Exception as exc:
            self.exception = exc
            if isinstance(exc, RayoHXError):
                return self._end(DownloadState.FAILED, started, message=exc.message, hint=exc.hint)
            logger.exception("The download failed unexpectedly.")
            return self._end(
                DownloadState.FAILED, started, message=f"Unexpected error: {redact_text(str(exc))}"
            )
        self._machine.move_to(DownloadState.COMPLETED)
        self._progress = dataclasses.replace(final, state=DownloadState.COMPLETED)
        self._emit(EventType.DOWNLOAD_COMPLETED, message=str(output.path), progress=self._progress)
        return DownloadResult(
            download_id=self._id,
            url=self._url,
            state=DownloadState.COMPLETED,
            elapsed_seconds=self._clock() - started,
            progress=self._progress,
            output=output,
        )

    def _execute(self) -> tuple[OutputInfo, DownloadProgress]:
        config = self._config
        self._emit(EventType.DOWNLOAD_STARTED, message=redact_url(self._url))
        self._move(DownloadState.INSPECTING)
        with HttpClient(
            config.network, origin_url=self._url, cancel=self._token, transport=self._transport
        ) as client:
            playlist = inspect_playlist(self._url, client)
            self._emit(EventType.PLAYLIST_LOADED, data={"kind": kind(playlist)})

            stream: StreamSelection | None = None
            if isinstance(playlist, MasterPlaylist):
                stream = select_stream(playlist, config.selection)
                self._emit(EventType.STREAM_SELECTED, data=describe(stream))
                media = load_media(client, stream.variant.uri)
                self._emit(EventType.PLAYLIST_LOADED, data={"kind": "media"})
            else:
                media = playlist

            self._move(DownloadState.PREPARING)
            require_single_stream(stream)
            container = media.container
            if container is ContainerFormat.UNKNOWN:
                container = probe_container(client, media)
            plan = plan_output(
                path=self._output,
                requested=config.output.format,
                container=container,
                url=self._url,
            )
            sink: OutputSink = (
                DirectorySink(plan.path, container, overwrite=config.output.overwrite)
                if plan.is_directory
                else FileSink(plan.path, overwrite=config.output.overwrite)
            )

            self._move(DownloadState.DOWNLOADING)
            summary = MediaDownload(
                media,
                client=client,
                config=config,
                sink=sink,
                variant=stream.variant if stream else None,
                events=self._bus,
                download_id=self._id,
                cancel=self._token,
                container=container,
                on_finalizing=self._finalizing,
            ).run()
        output = output_info(plan.path, summary, container)
        self._emit(EventType.FINALIZATION_COMPLETED, message=str(output.path))
        return output, summary.progress

    def _finalizing(self) -> None:
        self._move(DownloadState.FINALIZING)
        self._emit(EventType.FINALIZATION_STARTED, progress=self._progress)

    # --- bookkeeping -----------------------------------------------------------------------

    def _move(self, state: DownloadState) -> None:
        self._machine.move_to(state)

    def _end(
        self,
        state: DownloadState,
        started: float,
        *,
        message: str,
        hint: str | None = None,
    ) -> DownloadResult:
        self._machine.move_to(state)
        self._progress = dataclasses.replace(self._progress, state=state)
        kind = (
            EventType.DOWNLOAD_CANCELLED
            if state is DownloadState.CANCELLED
            else EventType.DOWNLOAD_FAILED
        )
        self._emit(kind, message=message, progress=self._progress, data={"hint": hint})
        return DownloadResult(
            download_id=self._id,
            url=self._url,
            state=state,
            elapsed_seconds=self._clock() - started,
            progress=self._progress,
            error=None if state is DownloadState.CANCELLED else join_message(message, hint),
        )

    def _remember_progress(self, event: DownloadEvent) -> None:
        if event.progress is not None:
            self._progress = event.progress

    def _emit(
        self,
        kind: EventType,
        *,
        message: str | None = None,
        progress: DownloadProgress | None = None,
        data: dict[str, object] | None = None,
    ) -> None:
        self._bus.emit(
            DownloadEvent(
                type=kind,
                download_id=self._id,
                state=self._machine.state,
                message=message,
                progress=progress,
                data=data or {},
            )
        )
