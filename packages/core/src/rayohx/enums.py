"""Enumerations shared across the engine."""

from enum import StrEnum


class DownloadState(StrEnum):
    """Where a download is in its life cycle."""

    QUEUED = "queued"
    INSPECTING = "inspecting"
    PREPARING = "preparing"
    DOWNLOADING = "downloading"
    FINALIZING = "finalizing"
    #: The finished file is being checked. The engine does not enter this state yet; a download
    #: may go from FINALIZING straight to COMPLETED.
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"

    @property
    def is_terminal(self) -> bool:
        """Whether no further state change is possible."""
        return self in {DownloadState.COMPLETED, DownloadState.FAILED, DownloadState.CANCELLED}


class SegmentState(StrEnum):
    """Where a single segment is in its life cycle."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class EventType(StrEnum):
    """Kinds of event the engine emits."""

    DOWNLOAD_STARTED = "download_started"
    PLAYLIST_LOADED = "playlist_loaded"
    STREAM_SELECTED = "stream_selected"
    SEGMENT_STARTED = "segment_started"
    SEGMENT_COMPLETED = "segment_completed"
    SEGMENT_FAILED = "segment_failed"
    DOWNLOAD_PROGRESS = "download_progress"
    FINALIZATION_STARTED = "finalization_started"
    FINALIZATION_COMPLETED = "finalization_completed"
    DOWNLOAD_COMPLETED = "download_completed"
    DOWNLOAD_FAILED = "download_failed"
    DOWNLOAD_CANCELLED = "download_cancelled"
    DOWNLOAD_PAUSED = "download_paused"
    DOWNLOAD_RESUMED = "download_resumed"
    #: A working folder was opened; ``data["path"]`` says where.
    WORKSPACE_OPENED = "workspace_opened"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_COMPLETED = "verification_completed"
    VERIFICATION_FAILED = "verification_failed"


class ContainerFormat(StrEnum):
    """How the segments of a stream are packaged."""

    MPEG_TS = "mpeg-ts"
    FMP4 = "fmp4"
    WEBVTT = "webvtt"
    #: Output only: a Matroska file.
    MATROSKA = "matroska"
    #: Output only: an audio file.
    AUDIO = "audio"
    UNKNOWN = "unknown"


class EncryptionMethod(StrEnum):
    """The ``METHOD`` of an ``EXT-X-KEY`` tag."""

    NONE = "NONE"
    AES_128 = "AES-128"
    SAMPLE_AES = "SAMPLE-AES"


class StorageStrategy(StrEnum):
    """How segment data moves from the network to the output."""

    AUTO = "auto"
    DIRECT = "direct"
    STREAMING = "streaming"
    BUFFERED = "buffered"
    TEMPORARY = "temporary"
    HYBRID = "hybrid"


class OutputFormat(StrEnum):
    """The kind of file the user asks for."""

    #: Follow the file name, else keep the stream's own container.
    AUTO = "auto"
    #: Keep the stream's own container exactly (a transport stream stays one). Nothing is
    #: re-wrapped, so separate audio tracks cannot be joined in.
    ORIGINAL = "original"
    TS = "ts"
    MP4 = "mp4"
    #: Matroska. Needs FFmpeg, which only copies the streams.
    MKV = "mkv"
    #: Only the sound, copied out into an audio file. Needs FFmpeg.
    AUDIO = "audio"
    SEGMENTS = "segments"


class RemuxBackend(StrEnum):
    """Which tool may remux the stream into the requested container."""

    AUTO = "auto"
    NATIVE = "native"
    FFMPEG = "ffmpeg"


class ErrorCategory(StrEnum):
    """What kind of problem an error is. Retry rules, reports and exit codes key off this."""

    URL = "url"
    CONFIGURATION = "configuration"
    PLAYLIST = "playlist"
    SELECTION = "selection"
    NETWORK = "network"
    HTTP = "http"
    AUTHENTICATION = "authentication"
    PROXY = "proxy"
    TLS = "tls"
    SEGMENT = "segment"
    CRYPTO = "crypto"
    STORAGE = "storage"
    OUTPUT = "output"
    REMUX = "remux"
    VERIFICATION = "verification"
    AUTOMATION = "automation"
    CANCELLATION = "cancellation"
    INTERNAL = "internal"


class Processing(StrEnum):
    """What was done to the data between the network and the output file.

    Streams are never re-encoded: ``TRANSCODED`` exists so a result can say so truthfully if that
    ever changes, and nothing produces it today.
    """

    #: The segments were joined; the data is unchanged.
    COPIED = "copied"
    #: The streams were copied into a different container.
    REMUXED = "remuxed"
    #: Separate tracks were joined into one file.
    MUXED = "muxed"
    #: One kind of stream (the sound) was taken out.
    EXTRACTED = "extracted"
    TRANSCODED = "transcoded"


class VerifyLevel(StrEnum):
    """How thoroughly a finished download is checked."""

    #: Only what every download does: HTTP status, sizes and segment signatures.
    NONE = "none"
    #: Also check the finished file: its container is readable and not empty.
    BASIC = "basic"
    #: Also look inside with ffprobe when it is installed: streams, duration, and stricter
    #: checks of every segment for cut-off data.
    STRONG = "strong"


class VerificationStatus(StrEnum):
    """Where the verification of a download stands."""

    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    FAILED = "failed"


class MetadataPolicy(StrEnum):
    """Which information about the media is written into the output file."""

    #: Write nothing.
    NONE = "none"
    #: Only the title and the language.
    MINIMAL = "minimal"
    #: Everything the stream tells us: title, description, language, chapters, artwork.
    PRESERVE = "preserve"
    #: Only what the settings give (``MetadataConfig.title`` and so on).
    CUSTOM = "custom"
