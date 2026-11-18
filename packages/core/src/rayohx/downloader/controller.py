"""The download controller: one object that takes a web address to a finished file.

It walks a download through its states (inspecting, preparing, downloading, finalizing), reports
each step as an event, and returns a structured result. A cancelled download ends as
``CANCELLED``, not as a failure. The command line, the API and the window all use this class.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from rayohx._download._output import plan_output
from rayohx._http import HttpClient
from rayohx._logs import set_download_id
from rayohx._mux.ffmpeg import find_ffmpeg
from rayohx._mux.source import probe_codecs
from rayohx._redaction import redact_text, redact_url
from rayohx.cancellation import CancellationToken
from rayohx.config import DownloadConfig, validate_url
from rayohx.downloader._delivery import Delivery, Rendition, check_free, subtitle_path
from rayohx.downloader._result import join_message, output_info
from rayohx.downloader._stream import (
    audio_codecs,
    describe,
    first_segment,
    kind,
    load_media,
    probe_container,
)
from rayohx.enums import ContainerFormat, DownloadState, EventType, OutputFormat, RemuxBackend
from rayohx.errors import (
    CancellationError,
    DownloadError,
    OutputFormatError,
    RayoHXError,
    UnsupportedCodecError,
)
from rayohx.events import DownloadEvent, DownloadStateMachine, EventBus
from rayohx.models import (
    DownloadProgress,
    DownloadResult,
    MasterPlaylist,
    OutputInfo,
)
from rayohx.playlist import inspect_playlist
from rayohx.stream import select_stream

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    import httpx

    from rayohx._download._output import OutputPlan
    from rayohx.models import MediaPlaylist, SubtitleTrack
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
        self._variables: Mapping[str, str] | None = None  # the master playlist's variables
        self._clock = clock
        self._pause_lock = threading.RLock()
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

    def pause(self) -> None:
        """Stop starting new segments until ``resume`` is called.

        Segments already being fetched finish first, so the pause takes a moment to show.
        Safe to call from any thread, before or during the download. It is a request: a
        download that is already finalizing carries on to the end.
        """
        self._token.pause()
        self._sync_pause_state()

    def resume(self) -> None:
        """Go on after ``pause``. Does nothing if the download is not paused."""
        self._token.resume()
        self._sync_pause_state()

    @property
    def is_paused(self) -> bool:
        """Whether the download is waiting for ``resume``."""
        return self._machine.state is DownloadState.PAUSED

    def _sync_pause_state(self) -> None:
        """Make the state and events agree with the token, when the download is downloading."""
        with self._pause_lock:
            wanted = self._token.is_paused
            state = self._machine.state
            if wanted and state is DownloadState.DOWNLOADING:
                self._machine.move_to(DownloadState.PAUSED)
                self._emit(EventType.DOWNLOAD_PAUSED, progress=self._progress)
            elif not wanted and state is DownloadState.PAUSED:
                self._machine.move_to(DownloadState.DOWNLOADING)
                self._emit(EventType.DOWNLOAD_RESUMED, progress=self._progress)

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
                self._variables = playlist.variables
                media = load_media(client, stream.variant.uri, self._variables)
                self._emit(EventType.PLAYLIST_LOADED, data={"kind": "media"})
            else:
                media = playlist

            self._move(DownloadState.PREPARING)
            container = media.container
            if container is ContainerFormat.UNKNOWN:
                container = probe_container(client, media)
            audios = self._renditions(client, stream)
            if config.output.format is OutputFormat.SEGMENTS and (
                audios or (stream and stream.subtitle_tracks)
            ):
                raise OutputFormatError(
                    "Separate audio and subtitle tracks cannot be saved as separate segments.",
                    hint="Set video_only to download just the video.",
                )
            plan = plan_output(
                path=self._output,
                requested=config.output.format,
                container=container,
                url=self._url,
                directory=config.output.directory,
                allow_remux=True,
                merge=bool(audios),
            )
            subtitles = self._subtitle_jobs(client, stream, plan)
            # Refuse before downloading anything if a file we will write is already there.
            targets = [path for _, _, path in subtitles]
            if not plan.is_directory:
                targets.append(plan.path)
            check_free(targets, config.output.overwrite)
            ffmpeg_path = self._choose_backend(client, media, container, audios, plan)

            delivery = Delivery(client, config, self._bus, self._id, self._token, self._finalizing)
            variant = stream.variant if stream else None
            self._move(DownloadState.DOWNLOADING)
            self._sync_pause_state()  # a pause requested before the download began
            shift: float | None = None
            if ffmpeg_path is not None:
                video_audio = audio_codecs(client, media, container)
                audios = [
                    dataclasses.replace(a, codecs=audio_codecs(client, a.media, a.container))
                    for a in audios
                ]
                summary = delivery.with_ffmpeg(
                    media, container, plan, variant, audios, ffmpeg_path, video_audio
                )
                result_container = ContainerFormat.FMP4
            elif plan.mux:
                summary, shift = delivery.native_mux(media, container, plan, variant, audios)
                result_container = ContainerFormat.FMP4
            else:
                summary = delivery.plain(media, container, plan, variant)
                result_container = container
            if subtitles:
                delivery.subtitles(subtitles, shift or 0.0)
        output = output_info(plan.path, summary, result_container)
        self._emit(EventType.FINALIZATION_COMPLETED, message=str(output.path))
        return output, summary.progress

    # --- preparing -------------------------------------------------------------------------

    def _renditions(self, client: HttpClient, stream: StreamSelection | None) -> list[Rendition]:
        """Load the playlists of the separate audio tracks that have to be joined in."""
        renditions = []
        for track in stream.audio_tracks if stream else ():
            assert track.uri is not None  # noqa: S101 - selection keeps only tracks with an address
            media = load_media(client, track.uri, self._variables)
            container = media.container
            if container is ContainerFormat.UNKNOWN:
                container = probe_container(client, media)
            if container not in {ContainerFormat.MPEG_TS, ContainerFormat.FMP4}:
                raise OutputFormatError(
                    f"The audio track {track.name!r} is in a form that cannot be joined in.",
                    hint="Only MPEG-TS and fragmented MP4 audio are supported.",
                )
            self._emit(EventType.PLAYLIST_LOADED, data={"kind": "media", "audio": track.name})
            renditions.append(Rendition(track, media, container))
        return renditions

    def _subtitle_jobs(
        self, client: HttpClient, stream: StreamSelection | None, plan: OutputPlan
    ) -> list[tuple[SubtitleTrack, MediaPlaylist, Path]]:
        """Load the playlists of the subtitle tracks and decide where each is saved."""
        jobs = []
        used: set[Path] = set()
        for track in stream.subtitle_tracks if stream else ():
            assert track.uri is not None  # noqa: S101 - selection keeps only tracks with an address
            media = load_media(client, track.uri, self._variables)
            if media.container not in {ContainerFormat.WEBVTT, ContainerFormat.UNKNOWN}:
                raise OutputFormatError(
                    f"The subtitles {track.name!r} are not WebVTT text, which is all that can "
                    "be saved.",
                    hint="Leave subtitles out, or set video_only.",
                )
            self._emit(EventType.PLAYLIST_LOADED, data={"kind": "media", "subtitles": track.name})
            jobs.append((track, media, subtitle_path(plan.path, track, used)))
        return jobs

    def _choose_backend(
        self,
        client: HttpClient,
        media: MediaPlaylist,
        container: ContainerFormat,
        audios: list[Rendition],
        plan: OutputPlan,
    ) -> Path | None:
        """Pick what re-wraps the stream: ``None`` for the built-in remuxer, else an FFmpeg."""
        if not plan.mux:
            return None
        wanted = self._config.output.remux_backend
        executable = find_ffmpeg(self._config.output.ffmpeg_path)
        if wanted is RemuxBackend.FFMPEG:
            if executable is None:
                raise OutputFormatError(
                    "FFmpeg was asked for but could not be found.",
                    hint="FFmpeg is an optional prerequisite: install it, or set its path in "
                    "the output settings.",
                )
            return executable
        inputs = [(media, container), *((audio.media, audio.container) for audio in audios)]
        try:
            for item, fmt in inputs:
                if fmt is ContainerFormat.MPEG_TS:
                    probe_codecs(first_segment(client, item).media)
        except UnsupportedCodecError as exc:
            if wanted is RemuxBackend.AUTO and executable is not None:
                logger.info("Using FFmpeg because the stream uses %s.", exc.codec)
                return executable
            hint = (
                "Set the remux backend to auto and install FFmpeg, an optional prerequisite."
                if wanted is RemuxBackend.NATIVE
                else "FFmpeg is not installed. It is an optional prerequisite for streams like "
                "this: install it, or set its path in the output settings."
            )
            raise UnsupportedCodecError(exc.codec, hint=hint) from exc
        return None

    def _finalizing(self) -> None:
        with self._pause_lock:
            if self._machine.state is DownloadState.PAUSED:
                self._machine.move_to(DownloadState.DOWNLOADING)
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
