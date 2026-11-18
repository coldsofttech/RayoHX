"""The ways a downloaded stream becomes an output file.

* **Plain**: the segments are joined as they are (MPEG-TS into ``.ts``, fragmented MP4 into
  ``.mp4``) or saved one file each.
* **Native mux**: the built-in remuxer re-wraps the stream into a fragmented MP4, joining in any
  separate audio tracks, which are first saved beside the output and read as needed.
* **FFmpeg**: for codecs the built-in remuxer cannot copy, an FFmpeg already installed copies the
  downloaded pieces into an MP4. It is never required, bundled or asked to transcode.

Subtitles are written next to the output as ``.vtt`` files.
"""

import dataclasses
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from rayohx._download._containers import validate_fmp4_file
from rayohx._download._media import DownloadSummary, MediaDownload
from rayohx._download._output import OutputPlan, sanitize_filename
from rayohx._download._sinks import DirectorySink, FileSink, OutputSink, StreamSink
from rayohx._http import HttpClient
from rayohx._mux import ffmpeg
from rayohx._mux.sink import MuxSink, TrackFile
from rayohx._mux.webvtt import merge_segments
from rayohx.cancellation import CancellationToken
from rayohx.config import DownloadConfig
from rayohx.enums import ContainerFormat, OutputFormat
from rayohx.errors import FinalizationError, OutputExistsError, OutputFormatError
from rayohx.events import EventBus
from rayohx.metadata.ffmpeg import prepare as prepare_metadata
from rayohx.metadata.model import MetadataInfo
from rayohx.models import AudioTrack, MediaPlaylist, SubtitleTrack, Variant

logger = logging.getLogger(__name__)

_EXTENSION = {ContainerFormat.MPEG_TS: ".ts", ContainerFormat.FMP4: ".mp4"}


@dataclass(frozen=True, slots=True)
class Rendition:
    """A separate audio track: its description, its playlist and what its segments are."""

    track: AudioTrack
    media: MediaPlaylist
    container: ContainerFormat
    #: The codecs of the track's audio streams (MPEG-TS only; filled in when FFmpeg is used).
    codecs: tuple[str, ...] = ()


@dataclass(slots=True)
class DeliveryNotes:
    """What a delivery has to say about how it went, beyond the file itself."""

    #: The metadata fields that were written into the output.
    metadata_written: tuple[str, ...] = ()
    #: Things the person should know, such as metadata that could not be written.
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Delivery:
    """Everything a delivery needs from the running download."""

    client: HttpClient
    config: DownloadConfig
    bus: EventBus | None
    download_id: str
    cancel: CancellationToken
    on_finalizing: Callable[[], None]
    report: DeliveryNotes = field(default_factory=DeliveryNotes)

    def _media_download(
        self,
        media: MediaPlaylist,
        *,
        sink: OutputSink,
        variant: Variant | None = None,
        container: ContainerFormat | None = None,
        output_container: ContainerFormat | None = None,
        on_finalizing: Callable[[], None] | None = None,
        config: DownloadConfig | None = None,
    ) -> MediaDownload:
        return MediaDownload(
            media,
            client=self.client,
            config=config or self.config,
            sink=sink,
            variant=variant,
            events=self.bus,
            download_id=self.download_id,
            cancel=self.cancel,
            container=container,
            output_container=output_container,
            on_finalizing=on_finalizing,
        )

    # --- plain -----------------------------------------------------------------------------

    def plain(
        self,
        media: MediaPlaylist,
        container: ContainerFormat,
        plan: OutputPlan,
        variant: Variant | None,
    ) -> DownloadSummary:
        """Join the segments as they are, or save them as separate files."""
        overwrite = self.config.output.overwrite
        sink = (
            DirectorySink(plan.path, container, overwrite=overwrite)
            if plan.is_directory
            else FileSink(plan.path, overwrite=overwrite)
        )
        return self._media_download(
            media,
            sink=sink,
            variant=variant,
            container=container,
            on_finalizing=self.on_finalizing,
        ).run()

    # --- native mux ------------------------------------------------------------------------

    def native_mux(
        self,
        media: MediaPlaylist,
        container: ContainerFormat,
        plan: OutputPlan,
        variant: Variant | None,
        audios: list[Rendition],
    ) -> tuple[DownloadSummary, float | None]:
        """Re-wrap the stream, and any separate audio, into a fragmented MP4.

        Returns the summary and the seconds taken off the timeline (for subtitles).
        """
        saved: list[Path] = []
        try:
            extras = []
            for number, audio in enumerate(audios):
                path = self._temporary(plan.path, f"audio{number}", audio.container)
                saved.append(path)
                self._save(audio, path)
                extras.append(
                    TrackFile(path, audio.container, audio.track.language, audio.track.name)
                )
            sink = MuxSink(
                plan.path, container, extras=extras, overwrite=self.config.output.overwrite
            )
            summary = self._media_download(
                media,
                sink=sink,
                variant=variant,
                container=container,
                output_container=ContainerFormat.FMP4,
                on_finalizing=self.on_finalizing,
            ).run()
            return summary, sink.origin
        finally:
            _remove(saved)

    # --- FFmpeg ----------------------------------------------------------------------------

    def with_ffmpeg(
        self,
        media: MediaPlaylist,
        container: ContainerFormat,
        plan: OutputPlan,
        variant: Variant | None,
        audios: list[Rendition],
        executable: Path,
        video_audio: tuple[str, ...] = (),
        metadata: MetadataInfo | None = None,
    ) -> DownloadSummary:
        """Download the pieces to files, then have FFmpeg copy them into one file.

        For audio-only output the video is not downloaded at all when the stream has a separate
        audio track: only that track is.
        """
        saved: list[Path] = []
        part = plan.path.with_name(plan.path.name + ".part")
        audio_only = plan.format is OutputFormat.AUDIO
        kind = "mkv" if plan.format is OutputFormat.MKV else "mp4"
        try:
            inputs: list[ffmpeg.FfmpegInput] = []
            if audio_only and audios:
                first = audios[0]
                path = self._temporary(plan.path, "audio0", first.container)
                saved.append(path)
                summary = self._media_download(
                    first.media,
                    sink=FileSink(path, overwrite=True),
                    container=first.container,
                    config=dataclasses.replace(self.config, resume=False),
                ).run()
                inputs.append(ffmpeg.FfmpegInput(path, first.codecs, first.track.language))
            else:
                video_path = self._temporary(plan.path, "video", container)
                saved.append(video_path)
                summary = self._media_download(
                    media,
                    sink=FileSink(video_path, overwrite=True),
                    variant=variant,
                    container=container,
                    config=dataclasses.replace(self.config, resume=False),
                ).run()
                inputs.append(ffmpeg.FfmpegInput(video_path, video_audio))
                for number, audio in enumerate(audios):
                    path = self._temporary(plan.path, f"audio{number}", audio.container)
                    saved.append(path)
                    self._save(audio, path)
                    inputs.append(ffmpeg.FfmpegInput(path, audio.codecs, audio.track.language))
            self.on_finalizing()
            self._check_free(plan.path)
            extras = (
                prepare_metadata(
                    metadata,
                    plan.path,
                    client=self.client,
                    total_duration=media.total_duration if media.is_vod else None,
                )
                if metadata is not None
                else None
            )
            if extras is not None:
                self.report.metadata_written = tuple(extras.written)
                self.report.notes.extend(extras.notes)
            try:
                ffmpeg.remux(
                    executable,
                    inputs,
                    part,
                    cancel=self.cancel,
                    kind=kind,
                    audio_only=audio_only,
                    metadata=extras,
                    target_suffix=plan.path.suffix,
                )
            finally:
                if extras is not None:
                    extras.cleanup()
            if plan.format is OutputFormat.MP4:
                validate_fmp4_file(part)
            elif not part.is_file() or part.stat().st_size == 0:
                raise FinalizationError("FFmpeg did not produce an output file.")
            self._place(part, plan.path)
            return dataclasses.replace(summary, output=plan.path)
        finally:
            part.unlink(missing_ok=True)
            _remove(saved)

    def _check_free(self, target: Path) -> None:
        if target.exists() and not self.config.output.overwrite:
            raise OutputExistsError(f"The output file already exists: {target}")

    def _place(self, part: Path, target: Path) -> None:
        self._check_free(target)
        os.replace(part, target)

    # --- pieces ----------------------------------------------------------------------------

    def _save(self, audio: Rendition, path: Path) -> None:
        """Download a separate track into a file, in full, with nothing kept for resuming."""
        self._media_download(
            audio.media,
            sink=FileSink(path, overwrite=True),
            container=audio.container,
            config=dataclasses.replace(self.config, resume=False),
        ).run()

    @staticmethod
    def _temporary(output: Path, label: str, container: ContainerFormat) -> Path:
        suffix = _EXTENSION.get(container, ".bin")
        return output.with_name(f".{output.name}.{label}{suffix}")

    # --- subtitles -------------------------------------------------------------------------

    def subtitles(
        self,
        tracks: list[tuple[SubtitleTrack, MediaPlaylist, Path]],
        shift: float,
    ) -> list[Path]:
        """Download each subtitle track and write it as a ``.vtt`` file."""
        written = []
        for track, media, path in tracks:
            texts: list[bytes] = []
            self._media_download(
                media,
                sink=StreamSink(texts.append),
                config=dataclasses.replace(self.config, resume=False),
            ).run()
            try:
                merged = merge_segments(
                    [text.decode("utf-8", errors="replace") for text in texts], shift
                )
            except OutputFormatError as exc:
                raise OutputFormatError(
                    f"The subtitles {track.name!r} are not in a supported form.",
                    hint=exc.message,
                ) from exc
            part = path.with_name(path.name + ".part")
            part.write_text(merged, encoding="utf-8")
            self._place(part, path)
            written.append(path)
        return written


def subtitle_path(output: Path, track: SubtitleTrack, used: set[Path]) -> Path:
    """Where a subtitle track is saved: ``<output name>.<language>.vtt``, made unique."""
    label = sanitize_filename(track.language or track.name, "subtitles")
    path = output.with_suffix(f".{label}.vtt")
    count = 2
    while path in used:
        path = output.with_suffix(f".{label}{count}.vtt")
        count += 1
    used.add(path)
    return path


def check_free(paths: list[Path], overwrite: bool) -> None:
    """Fail early if a file we are about to write already exists."""
    if overwrite:
        return
    for path in paths:
        if path.exists():
            raise OutputExistsError(
                f"The output file already exists: {path}",
                hint="Choose another name or allow overwriting.",
            )


def _remove(paths: list[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)
        path.with_name(path.name + ".part").unlink(missing_ok=True)
