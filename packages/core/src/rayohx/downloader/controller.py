"""The download controller: one object that takes a web address to a finished file.

It walks a download through its states (inspecting, preparing, downloading, finalizing), reports
each step as an event, and returns a structured result. A cancelled download ends as
``CANCELLED``, not as a failure. The command line, the API and the window all use this class.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from rayohx._download._output import audio_suffix, plan_output
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
from rayohx.enums import (
    ContainerFormat,
    DownloadState,
    EventType,
    OutputFormat,
    Processing,
    RemuxBackend,
)
from rayohx.errors import (
    CancellationError,
    DownloadError,
    OutputFormatError,
    RayoHXError,
    UnsupportedCodecError,
    VerificationError,
)
from rayohx.events import DownloadEvent, DownloadStateMachine, EventBus
from rayohx.metadata import MetadataInfo, effective_metadata, extract_metadata
from rayohx.models import (
    DownloadProgress,
    DownloadResult,
    MasterPlaylist,
    OutputInfo,
)
from rayohx.playlist import inspect_playlist, inspect_text
from rayohx.stream import select_stream
from rayohx.verify import Expectations, verify_output

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    import httpx

    from rayohx._download._output import OutputPlan
    from rayohx.models import MediaPlaylist, SubtitleTrack
    from rayohx.stream import StreamSelection
    from rayohx.verify import IntegrityReport

logger = logging.getLogger(__name__)

#: What the file is called in the result, for the formats FFmpeg makes (MP4 is the default).
_FFMPEG_CONTAINER = {
    OutputFormat.MKV: ContainerFormat.MATROSKA,
    OutputFormat.AUDIO: ContainerFormat.AUDIO,
}


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
        playlist_text: str | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = validate_url(url)
        self._config = config or DownloadConfig()
        self._output = Path(output) if output is not None else self._config.output.path
        self._bus = events if events is not None else EventBus()
        self._token = cancel if cancel is not None else CancellationToken()
        self._id = download_id or uuid.uuid4().hex[:12]
        self._transport = transport
        self._playlist_text = playlist_text
        self._variables: Mapping[str, str] | None = None  # the master playlist's variables
        self._clock = clock
        self._pause_lock = threading.RLock()
        self._machine = DownloadStateMachine()
        self._progress = DownloadProgress()
        self._ran = False
        self._integrity: IntegrityReport | None = None
        self._metadata = MetadataInfo()
        self._notes: list[str] = []
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
            integrity=self._integrity,
            notes=tuple(self._notes),
        )

    def _execute(self) -> tuple[OutputInfo, DownloadProgress]:
        config = self._config
        self._emit(EventType.DOWNLOAD_STARTED, message=redact_url(self._url))
        self._move(DownloadState.INSPECTING)
        with HttpClient(
            config.network, origin_url=self._url, cancel=self._token, transport=self._transport
        ) as client:
            playlist = (
                inspect_playlist(self._url, client)
                if self._playlist_text is None
                else inspect_text(self._playlist_text, self._url)
            )
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
            audio_tracks = tuple(a.track for a in audios)
            info = extract_metadata(
                playlist if isinstance(playlist, MasterPlaylist) else None,
                media,
                url=self._url,
                audio=audio_tracks,
            )
            self._metadata = effective_metadata(info, config.metadata)
            plan = plan_output(
                path=self._chosen_output(info),
                requested=config.output.format,
                container=container,
                url=self._url,
                directory=config.output.directory,
                allow_remux=True,
                merge=bool(audios),
            )
            if plan.format is OutputFormat.AUDIO:
                # One audio file: the first selected track, and no subtitles.
                audios = audios[:1]
                stream = None
            if plan.via_ffmpeg:
                self._require_ffmpeg(plan)  # before any segment is fetched
                plan = self._with_audio_suffix(client, media, container, audios, plan)
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
                video_audio = (
                    ()
                    if plan.format is OutputFormat.AUDIO and audios
                    else audio_codecs(client, media, container)
                )
                audios = [
                    dataclasses.replace(a, codecs=audio_codecs(client, a.media, a.container))
                    for a in audios
                ]
                summary = delivery.with_ffmpeg(
                    media,
                    container,
                    plan,
                    variant,
                    audios,
                    ffmpeg_path,
                    video_audio,
                    self._metadata if not self._metadata.empty else None,
                )
                result_container = _FFMPEG_CONTAINER.get(plan.format, ContainerFormat.FMP4)
                processing = (
                    Processing.EXTRACTED
                    if plan.format is OutputFormat.AUDIO
                    else Processing.MUXED
                    if audios
                    else Processing.REMUXED
                )
            elif plan.mux:
                self._note_unwritten_metadata(plan)
                summary, shift = delivery.native_mux(media, container, plan, variant, audios)
                result_container = ContainerFormat.FMP4
                processing = Processing.MUXED if audios else Processing.REMUXED
            else:
                self._note_unwritten_metadata(plan)
                summary = delivery.plain(media, container, plan, variant)
                result_container = container
                processing = Processing.COPIED
            if subtitles:
                delivery.subtitles(subtitles, shift or 0.0)
        output = output_info(plan.path, summary, result_container, processing)
        output = dataclasses.replace(output, metadata=delivery.report.metadata_written)
        self._notes.extend(delivery.report.notes)
        self._emit(EventType.FINALIZATION_COMPLETED, message=str(output.path))
        self._verify(output, media, audios, plan, summary.total_segments)
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
        if plan.via_ffmpeg:
            return self._require_ffmpeg(plan)
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

    def _verify(
        self,
        output: OutputInfo,
        media: MediaPlaylist,
        audios: list[Rendition],
        plan: OutputPlan,
        segments: int,
    ) -> None:
        """Check the finished output as the settings ask. Raises if it does not pass."""
        settings = self._config.verify
        if not settings.requested:
            return
        if self._machine.state in {DownloadState.DOWNLOADING, DownloadState.PAUSED}:
            self._finalizing()  # a path that did not announce finalizing
        self._move(DownloadState.VERIFYING)
        self._emit(
            EventType.VERIFICATION_STARTED,
            message=settings.level.value,
            progress=self._progress,
        )
        audio_only = plan.format is OutputFormat.AUDIO
        report = verify_output(
            output.path,
            container=output.container,
            config=settings,
            expected=Expectations(
                duration=media.total_duration if media.is_vod and media.segments else None,
                video=not audio_only,
                audio=audio_only or bool(audios),
                segments=segments,
            ),
            cancel=self._token,
        )
        if not report.verified:
            report = self._set_aside(output.path, report, keep=settings.keep_invalid)
        self._integrity = report
        self._emit(
            EventType.VERIFICATION_COMPLETED if report.verified else EventType.VERIFICATION_FAILED,
            message=report.summary(),
            data=report.to_dict(),
        )
        if not report.verified:
            hint = (
                f"The file was kept as {report.invalid_path}."
                if report.invalid_path
                else "The file was removed."
            )
            raise VerificationError(report.summary(), hint=hint)

    @staticmethod
    def _set_aside(path: Path, report: IntegrityReport, *, keep: bool) -> IntegrityReport:
        """Never leave a file that failed verification under its proper name."""
        invalid: Path | None = None
        try:
            if path.is_file() and keep:
                invalid = path.with_name(path.name + ".invalid")
                os.replace(path, invalid)
            elif path.is_file():
                path.unlink()
        except OSError:
            logger.warning("The output that failed verification could not be moved aside.")
            invalid = None
        return dataclasses.replace(report, invalid_path=str(invalid) if invalid else None)

    def _chosen_output(self, info: MetadataInfo) -> Path | None:
        """The output path: the one asked for, else one made from the name template."""
        if self._output is not None:
            return self._output
        template = self._config.output.name_template
        if not template:
            return None
        from rayohx.naming import render_template, standard_tokens

        title = self._config.metadata.title or info.title
        language = self._config.metadata.language or info.language
        stem = render_template(
            template, standard_tokens(url=self._url, title=title, language=language)
        )
        return (self._config.output.directory or Path.cwd()) / stem

    def _note_unwritten_metadata(self, plan: OutputPlan) -> None:
        """Say so when metadata was wanted but this way of making the file cannot hold it."""
        if self._metadata.empty and not self._metadata.description:
            return
        if plan.is_directory:
            return
        self._notes.append(
            "Metadata was not written: files made without FFmpeg cannot hold it. "
            "Use Matroska or audio output, or set the remux backend to ffmpeg."
        )

    def _require_ffmpeg(self, plan: OutputPlan) -> Path:
        """The FFmpeg that Matroska and audio-only output need, or an explanation."""
        what = "Matroska" if plan.format is OutputFormat.MKV else "Audio-only"
        if self._config.output.remux_backend is RemuxBackend.NATIVE:
            raise OutputFormatError(
                f"{what} output needs FFmpeg, but only the built-in remuxer is allowed.",
                hint="Set the remux backend to auto or ffmpeg.",
            )
        executable = find_ffmpeg(self._config.output.ffmpeg_path)
        if executable is None:
            raise OutputFormatError(
                f"{what} output needs FFmpeg, which could not be found.",
                hint="FFmpeg is an optional prerequisite: install it, or set its path in "
                "the output settings.",
            )
        return executable

    def _with_audio_suffix(
        self,
        client: HttpClient,
        media: MediaPlaylist,
        container: ContainerFormat,
        audios: list[Rendition],
        plan: OutputPlan,
    ) -> OutputPlan:
        """Give an audio file the extension that suits its codec (when the name left it open)."""
        if not plan.suffix_pending:
            return plan
        source, kind_ = (audios[0].media, audios[0].container) if audios else (media, container)
        suffix = audio_suffix(audio_codecs(client, source, kind_), kind_)
        return dataclasses.replace(plan, path=plan.path.with_suffix(suffix), suffix_pending=False)

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
            integrity=self._integrity,
            notes=tuple(self._notes),
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
