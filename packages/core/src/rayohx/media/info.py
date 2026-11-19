"""What a stream offers, in detail, before anything is downloaded.

``inspect_media`` reads the playlists and, when asked and ffprobe is installed, the first segment,
and returns a ``MediaInfo``. Every value says where it came from, and values that cannot be known
are ``None`` rather than guessed: the size, for example, is ``exact``, an ``estimate`` or
``unavailable``, and an estimate always says what it is based on.
"""

from __future__ import annotations

import contextlib
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rayohx import _http
from rayohx._redaction import redact_url
from rayohx.capabilities import Capabilities, detect
from rayohx.config import NetworkConfig, SelectionConfig
from rayohx.enums import ContainerFormat, OutputFormat
from rayohx.media.codecs import describe_codec
from rayohx.media.probe import FileInfo, StreamDetails, find_ffprobe, probe_file
from rayohx.metadata import MetadataInfo, extract_metadata
from rayohx.models import MasterPlaylist, MediaPlaylist

if TYPE_CHECKING:
    import httpx

    from rayohx.models import AudioTrack, Variant
    from rayohx.stream import StreamSelection

logger = logging.getLogger(__name__)

#: Used only to estimate a separate audio track, whose bit rate the playlist does not give.
ASSUMED_AUDIO_BITS_PER_SECOND = 128_000
MAX_PROBE_BYTES = 16 * 1024 * 1024

_LABELS = {
    ContainerFormat.MPEG_TS: "MPEG-TS",
    ContainerFormat.FMP4: "fragmented MP4",
    ContainerFormat.WEBVTT: "WebVTT",
}
#: Codecs the built-in remuxer can copy into an MP4 (anything else needs FFmpeg).
_NATIVE_VIDEO = frozenset({"h264", "hevc"})
_NATIVE_AUDIO = frozenset({"aac", "ac3", "eac3", "mp3"})


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if v is not None and v != [] and v != {}}


@dataclass(frozen=True, slots=True, kw_only=True)
class SizeInfo:
    """How big the download will be, and how sure we are."""

    #: ``exact`` (every byte is accounted for), ``estimated`` or ``unavailable``.
    kind: str
    bytes: int | None = None
    #: What the figure is based on.
    basis: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "bytes": self.bytes, "basis": self.basis}


@dataclass(frozen=True, slots=True, kw_only=True)
class VideoInfo:
    codec: str | None = None
    #: A name to show, such as ``H.264 High@4.0``.
    label: str | None = None
    profile: str | None = None
    level: str | None = None
    width: int | None = None
    height: int | None = None
    frame_rate: float | None = None
    bit_rate: int | None = None
    pixel_format: str | None = None
    video_range: str | None = None
    #: ``playlist`` (what the playlist says) or ``probe`` (read from the media).
    source: str = "playlist"

    def to_dict(self) -> dict[str, Any]:
        return _clean(
            {
                "codec": self.codec, "label": self.label, "profile": self.profile,
                "level": self.level, "width": self.width, "height": self.height,
                "frame_rate": self.frame_rate, "bit_rate": self.bit_rate,
                "pixel_format": self.pixel_format, "video_range": self.video_range,
                "source": self.source,
            }
        )  # fmt: skip


@dataclass(frozen=True, slots=True, kw_only=True)
class AudioInfo:
    codec: str | None = None
    label: str | None = None
    name: str | None = None
    language: str | None = None
    channels: int | None = None
    channel_layout: str | None = None
    sample_rate: int | None = None
    bit_rate: int | None = None
    default: bool = False
    #: Whether this track is separate from the video (a ``EXT-X-MEDIA`` rendition).
    separate: bool = False
    #: Whether a download with these settings picks it.
    selected: bool = False
    source: str = "playlist"

    def to_dict(self) -> dict[str, Any]:
        return _clean(
            {
                "codec": self.codec, "label": self.label, "name": self.name,
                "language": self.language, "channels": self.channels,
                "channel_layout": self.channel_layout, "sample_rate": self.sample_rate,
                "bit_rate": self.bit_rate, "default": self.default, "separate": self.separate,
                "selected": self.selected, "source": self.source,
            }
        )  # fmt: skip


@dataclass(frozen=True, slots=True, kw_only=True)
class SubtitleInfo:
    name: str
    language: str | None = None
    default: bool = False
    forced: bool = False
    selected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _clean(
            {
                "name": self.name, "language": self.language, "default": self.default,
                "forced": self.forced, "selected": self.selected,
            }
        )  # fmt: skip


@dataclass(frozen=True, slots=True, kw_only=True)
class VariantInfo:
    """One of the streams a master playlist offers."""

    index: int
    bandwidth: int
    average_bandwidth: int | None = None
    width: int | None = None
    height: int | None = None
    frame_rate: float | None = None
    video_range: str | None = None
    codecs: tuple[str, ...] = ()
    selected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _clean(
            {
                "index": self.index, "bandwidth": self.bandwidth,
                "average_bandwidth": self.average_bandwidth, "width": self.width,
                "height": self.height, "frame_rate": self.frame_rate,
                "video_range": self.video_range, "codecs": list(self.codecs),
                "selected": self.selected,
            }
        )  # fmt: skip


@dataclass(frozen=True, slots=True)
class CompatibilityNote:
    """Something to know before saving in a given format."""

    level: str  # "error", "warning" or "info"
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"level": self.level, "message": self.message}


@dataclass(frozen=True, slots=True, kw_only=True)
class MediaInfo:
    """What a stream offers and what a download with the given settings would take."""

    url: str
    #: ``master`` (a list of streams) or ``media`` (one stream).
    kind: str
    duration: float | None
    live: bool
    segment_count: int
    #: Segments that follow a break in the stream (``EXT-X-DISCONTINUITY``).
    discontinuities: int
    #: The longest a segment may last, as the playlist promises.
    target_duration: float | None
    #: How the segments are packaged: ``MPEG-TS``, ``fragmented MP4`` ...
    container: str | None
    #: ``AES-128``, ``SAMPLE-AES`` or ``None``.
    encryption: str | None
    size: SizeInfo
    video: VideoInfo | None
    audio: tuple[AudioInfo, ...] = ()
    subtitles: tuple[SubtitleInfo, ...] = ()
    variants: tuple[VariantInfo, ...] = ()
    metadata: MetadataInfo = field(default_factory=MetadataInfo)
    notes: tuple[str, ...] = ()

    @property
    def title(self) -> str | None:
        return self.metadata.title

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "kind": self.kind,
            "title": self.title,
            "duration": self.duration,
            "live": self.live,
            "segment_count": self.segment_count,
            "discontinuities": self.discontinuities,
            "target_duration": self.target_duration,
            "container": self.container,
            "encryption": self.encryption,
            "size": self.size.to_dict(),
            "video": self.video.to_dict() if self.video else None,
            "audio": [a.to_dict() for a in self.audio],
            "subtitles": [s.to_dict() for s in self.subtitles],
            "variants": [v.to_dict() for v in self.variants],
            "metadata": self.metadata.to_dict(),
            "notes": list(self.notes),
        }


# --- building it -------------------------------------------------------------------------------


def estimate_size(
    media: MediaPlaylist,
    variant: Variant | None,
    separate_audio: int,
) -> SizeInfo:
    """The size of a download, as honestly as the playlist allows."""
    if not media.is_vod or not media.segments:
        return SizeInfo(kind="unavailable", basis="a live stream has no end")
    ranges = [s.byte_range.length for s in media.segments if s.byte_range is not None]
    if len(ranges) == len(media.segments) and not separate_audio:
        return SizeInfo(kind="exact", bytes=sum(ranges), basis="the byte ranges in the playlist")
    if variant is None or not variant.bandwidth:
        return SizeInfo(kind="unavailable", basis="the playlist gives no bit rate")
    if variant.average_bandwidth:
        rate, basis = variant.average_bandwidth, "average bandwidth x duration"
    else:
        rate, basis = variant.bandwidth, "peak bandwidth x duration (an upper bound)"
    bits = rate + separate_audio * ASSUMED_AUDIO_BITS_PER_SECOND
    if separate_audio:
        basis += f", plus {ASSUMED_AUDIO_BITS_PER_SECOND // 1000} kbit/s assumed per audio track"
    return SizeInfo(kind="estimated", bytes=int(bits * media.total_duration / 8), basis=basis)


def _video_from_playlist(variant: Variant | None) -> VideoInfo | None:
    if variant is None:
        return None
    described = next(
        (describe_codec(c) for c in variant.codecs if describe_codec(c).kind == "video"), None
    )
    resolution = variant.resolution
    return VideoInfo(
        codec=described.codec if described else None,
        label=described.label if described else None,
        profile=described.profile if described else None,
        level=described.level if described else None,
        width=resolution.width if resolution else None,
        height=resolution.height if resolution else None,
        frame_rate=variant.frame_rate,
        bit_rate=variant.average_bandwidth or variant.bandwidth or None,
        video_range=variant.video_range,
    )


def _muxed_audio(variant: Variant | None) -> list[AudioInfo]:
    """Audio the codec list says is inside the video segments."""
    if variant is None:
        return []
    found = []
    for text in variant.codecs:
        described = describe_codec(text)
        if described.kind == "audio":
            found.append(AudioInfo(codec=described.codec, label=described.label, default=True))
    return found


def _track_audio(track: AudioTrack, selected: bool, codecs: tuple[str, ...]) -> AudioInfo:
    described = next((describe_codec(c) for c in codecs if describe_codec(c).kind == "audio"), None)
    channels = None
    if track.channels:
        head = track.channels.split("/")[0]
        channels = int(head) if head.isdigit() else None
    return AudioInfo(
        codec=described.codec if described else None,
        label=described.label if described else None,
        name=track.name,
        language=track.language,
        channels=channels,
        default=track.default,
        separate=track.uri is not None,
        selected=selected,
    )


def _apply_probe(
    video: VideoInfo | None, audio: list[AudioInfo], info: FileInfo, *, muxed: bool
) -> tuple[VideoInfo | None, list[AudioInfo]]:
    """Fill in what ffprobe saw in the first segment."""
    streams: list[StreamDetails] = info.of_kind("video")
    if streams:
        seen = streams[0]
        base = video or VideoInfo()
        video = VideoInfo(
            codec=seen.codec or base.codec,
            label=base.label,
            profile=seen.profile or base.profile,
            level=base.level,
            width=seen.width or base.width,
            height=seen.height or base.height,
            frame_rate=seen.frame_rate or base.frame_rate,
            bit_rate=seen.bit_rate or base.bit_rate,
            pixel_format=seen.pixel_format,
            video_range=base.video_range,
            source="probe",
        )
    heard = info.of_kind("audio")
    if muxed and heard:
        audio = [
            AudioInfo(
                codec=s.codec,
                label=audio[i].label if i < len(audio) else None,
                name=audio[i].name if i < len(audio) else None,
                language=s.language or (audio[i].language if i < len(audio) else None),
                channels=s.channels,
                channel_layout=s.channel_layout,
                sample_rate=s.sample_rate,
                bit_rate=s.bit_rate,
                default=i == 0,
                selected=True,
                source="probe",
            )
            for i, s in enumerate(heard)
        ]
    return video, audio


def _probe_first_segment(
    client: _http.HttpClient, media: MediaPlaylist, ffprobe: Path | None
) -> FileInfo:
    from rayohx.downloader._stream import first_segment

    data = first_segment(client, media)
    blob = data.init + data.media
    if len(blob) > MAX_PROBE_BYTES:
        blob = blob[:MAX_PROBE_BYTES]
    suffix = ".ts" if not data.init else ".mp4"
    with tempfile.TemporaryDirectory(prefix="rayohx-probe-") as folder:
        path = Path(folder) / f"first{suffix}"
        path.write_bytes(blob)
        return probe_file(path, ffprobe)


def inspect_media(
    url: str,
    *,
    network: NetworkConfig | None = None,
    selection: SelectionConfig | None = None,
    playlist_text: str | None = None,
    probe: bool = True,
    ffprobe: Path | str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> MediaInfo:
    """Describe a stream in detail without downloading it.

    ``selection`` says which stream, audio and subtitle tracks a download would take; they are
    marked ``selected``. With ``probe`` (and ffprobe installed) the first segment is fetched and
    examined, which fills in the profile, frame rate, channels and sample rate. Without it only
    the playlists are read, and nothing is guessed that they do not say.

    Raises:
        ConfigurationError: If ``url`` is not a web address.
        PlaylistError, NetworkError: As ``rayohx.inspect`` does.
    """
    from rayohx.downloader._stream import load_media, probe_container
    from rayohx.playlist import inspect_playlist, inspect_text
    from rayohx.stream import select_stream

    notes: list[str] = []
    config = selection or SelectionConfig()
    program = find_ffprobe(ffprobe) if probe else None
    with _http.HttpClient(
        network or NetworkConfig(), origin_url=url, transport=transport
    ) as client:
        playlist = (
            inspect_playlist(url, client)
            if playlist_text is None
            else inspect_text(playlist_text, url)
        )
        master: MasterPlaylist | None = None
        stream: StreamSelection | None = None
        if isinstance(playlist, MasterPlaylist):
            master = playlist
            stream = select_stream(master, config)
            notes += list(stream.notes)
            media = load_media(client, stream.variant.uri, master.variables)
        else:
            media = playlist
        container = media.container
        if container is ContainerFormat.UNKNOWN and probe and media.segments:
            with contextlib.suppress(Exception):
                container = probe_container(client, media)
        variant = stream.variant if stream else None
        video = _video_from_playlist(variant)
        audio: list[AudioInfo] = []
        separate: list[AudioInfo] = []
        subtitles: list[SubtitleInfo] = []
        if master is not None and variant is not None:
            chosen = {t.uri for t in stream.audio_tracks} if stream else set()
            group = master.audio_group(variant.audio_group) if variant.audio_group else ()
            separate = [_track_audio(t, t.uri in chosen, variant.codecs) for t in group if t.uri]
            if not separate:  # the audio the codec list names is inside the video segments
                audio = _muxed_audio(variant)
            picked = {t.uri for t in stream.subtitle_tracks} if stream else set()
            for t in (
                master.subtitle_group(variant.subtitle_group) if variant.subtitle_group else ()
            ):
                subtitles.append(
                    SubtitleInfo(
                        name=t.name, language=t.language, default=t.default, forced=t.forced,
                        selected=t.uri in picked,
                    )
                )  # fmt: skip
        if program is not None and media.segments:
            try:
                found = _probe_first_segment(client, media, program)
                video, audio = _apply_probe(video, audio, found, muxed=not separate)
            except Exception as exc:
                notes.append(f"The first segment could not be examined: {exc}")
        elif probe and program is None:
            notes.append("ffprobe is not installed, so only what the playlist says is shown.")
        info_meta = extract_metadata(
            master, media, url=url, audio=tuple(stream.audio_tracks) if stream else ()
        )
    all_audio = tuple(audio) + tuple(separate)
    encryption = next(
        (s.encryption.method.value for s in media.segments if s.encryption is not None), None
    )
    variants: tuple[VariantInfo, ...] = ()
    if master is not None:
        variants = tuple(
            VariantInfo(
                index=i,
                bandwidth=v.bandwidth,
                average_bandwidth=v.average_bandwidth,
                width=v.resolution.width if v.resolution else None,
                height=v.resolution.height if v.resolution else None,
                frame_rate=v.frame_rate,
                video_range=v.video_range,
                codecs=v.codecs,
                selected=v is variant,
            )
            for i, v in enumerate(master.variants, start=1)
        )
    picked_separate = sum(1 for a in separate if a.selected)
    return MediaInfo(
        url=redact_url(url),
        kind="master" if master is not None else "media",
        duration=media.total_duration if media.is_vod and media.segments else None,
        live=not media.is_vod,
        segment_count=media.segment_count,
        discontinuities=sum(1 for s in media.segments if s.discontinuity),
        target_duration=media.target_duration or None,
        container=_LABELS.get(container),
        encryption=encryption,
        size=estimate_size(media, variant, picked_separate),
        video=video,
        audio=all_audio,
        subtitles=tuple(subtitles),
        variants=variants,
        metadata=info_meta,
        notes=tuple(notes),
    )


# --- will it work ------------------------------------------------------------------------------


def check_compatibility(
    info: MediaInfo, output: OutputFormat, capabilities: Capabilities | None = None
) -> list[CompatibilityNote]:
    """What to know before saving ``info`` as ``output``: problems first, then hints."""
    caps = capabilities if capabilities is not None else detect()
    notes: list[CompatibilityNote] = []
    add = notes.append
    if info.live:
        add(CompatibilityNote("error", "This is a live stream, which cannot be downloaded."))
    if info.encryption == "SAMPLE-AES":
        add(CompatibilityNote("error", "SAMPLE-AES encrypted streams are not supported."))
    if output in {OutputFormat.MKV, OutputFormat.AUDIO} and caps.ffmpeg is None:
        add(CompatibilityNote("error", f"{output.value} output needs FFmpeg, which was not found."))
    packaged = info.container
    if output is OutputFormat.TS and packaged == "fragmented MP4":
        add(CompatibilityNote("error", "This stream is fragmented MP4 and cannot be saved as TS."))
    separate = [a for a in info.audio if a.separate and a.selected]
    if output is OutputFormat.ORIGINAL and separate:
        add(CompatibilityNote("error", "The original format cannot hold a separate audio track."))
    if output is OutputFormat.SEGMENTS and (separate or any(s.selected for s in info.subtitles)):
        add(
            CompatibilityNote(
                "error", "Separate audio and subtitle tracks cannot be saved as separate segments."
            )
        )
    if output in {OutputFormat.MP4, OutputFormat.AUTO} and packaged == "MPEG-TS":
        video_codec = info.video.codec if info.video else None
        odd = [c for c in ([video_codec] if video_codec else []) if c not in _NATIVE_VIDEO]
        odd += [a.codec for a in info.audio if a.codec and a.codec not in _NATIVE_AUDIO]
        if odd and output is OutputFormat.MP4:
            wording = (
                "FFmpeg will be used" if caps.ffmpeg else "FFmpeg is needed, but was not found"
            )
            add(
                CompatibilityNote(
                    "warning" if caps.ffmpeg else "error",
                    f"The built-in remuxer cannot copy {', '.join(sorted(set(odd)))} into an MP4: "
                    f"{wording}.",
                )
            )
    if any(s.selected for s in info.subtitles):
        add(
            CompatibilityNote(
                "info", "Subtitles are saved as separate .vtt files beside the video."
            )
        )
    wants = info.metadata.title or info.metadata.chapters or info.metadata.artwork_url
    if wants and output in {OutputFormat.TS, OutputFormat.ORIGINAL, OutputFormat.SEGMENTS}:
        add(CompatibilityNote("info", "This kind of file cannot hold the stream's metadata."))
    notes.sort(key=lambda n: {"error": 0, "warning": 1, "info": 2}[n.level])
    return notes
