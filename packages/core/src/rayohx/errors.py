"""Exceptions raised by the engine.

Every message passes through the redactor, so a credential in a URL, header or free text never
reaches a log line or a traceback. Each exception can carry a ``hint`` that tells the user what to
try next.
"""

from typing import ClassVar

from rayohx._redaction import redact_text, redact_url
from rayohx.enums import ErrorCategory


def format_bytes(size: int) -> str:
    """Return ``size`` in a short human-readable form such as ``1.5 GiB``."""
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(value) < 1024 or unit == "TiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError  # pragma: no cover - the loop always returns


class RayoHXError(Exception):
    """Base class of every error the engine raises on purpose.

    Every class has a stable ``code`` and a ``category``. Reports, retry rules and exit codes use
    these, never the message text, which may change.
    """

    error_code: ClassVar[str] = "ERROR"
    category: ClassVar[ErrorCategory] = ErrorCategory.INTERNAL

    @property
    def code(self) -> str:
        """A short, stable identifier such as ``HTTP_403`` or ``STORAGE_LOW``."""
        return self.error_code

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        self.message = redact_text(message)
        self.hint = redact_text(hint) if hint else None
        super().__init__(self.message)

    def describe(self) -> str:
        """Return the message followed by the hint, when there is one."""
        return f"{self.message} {self.hint}" if self.hint else self.message


class ConfigurationError(RayoHXError):
    """A setting is missing, malformed or contradicts another setting."""

    error_code: ClassVar[str] = "CONFIGURATION_INVALID"
    category: ClassVar[ErrorCategory] = ErrorCategory.CONFIGURATION


class PlaylistError(RayoHXError):
    """A playlist could not be used."""

    error_code: ClassVar[str] = "PLAYLIST_ERROR"
    category: ClassVar[ErrorCategory] = ErrorCategory.PLAYLIST


class InvalidPlaylistError(PlaylistError):
    """A playlist is malformed."""

    error_code: ClassVar[str] = "PLAYLIST_INVALID"
    category: ClassVar[ErrorCategory] = ErrorCategory.PLAYLIST

    def __init__(self, message: str, *, line: int | None = None, hint: str | None = None) -> None:
        self.line = line
        super().__init__(f"{message} (line {line})" if line is not None else message, hint=hint)


class UnsupportedPlaylistError(PlaylistError):
    """A playlist is valid but uses something the engine does not support."""

    error_code: ClassVar[str] = "PLAYLIST_UNSUPPORTED"
    category: ClassVar[ErrorCategory] = ErrorCategory.PLAYLIST


class PlaylistNotFoundError(PlaylistError):
    """The playlist address does not exist."""

    error_code: ClassVar[str] = "PLAYLIST_NOT_FOUND"
    category: ClassVar[ErrorCategory] = ErrorCategory.PLAYLIST


class NetworkError(RayoHXError):
    """A request failed."""

    error_code: ClassVar[str] = "NETWORK_ERROR"
    category: ClassVar[ErrorCategory] = ErrorCategory.NETWORK

    _retryable_default = False

    def __init__(
        self, message: str, *, hint: str | None = None, retryable: bool | None = None
    ) -> None:
        super().__init__(message, hint=hint)
        self._retryable = retryable

    @property
    def retryable(self) -> bool:
        """Whether trying the same request again could succeed."""
        return self._retryable_default if self._retryable is None else self._retryable


class NetworkConnectionError(NetworkError):
    """The server could not be reached, or the connection broke."""

    error_code: ClassVar[str] = "NETWORK_CONNECTION"
    category: ClassVar[ErrorCategory] = ErrorCategory.NETWORK

    _retryable_default = True


class NetworkTimeoutError(NetworkConnectionError):
    """A connect, read or overall timeout expired."""

    error_code: ClassVar[str] = "NETWORK_TIMEOUT"
    category: ClassVar[ErrorCategory] = ErrorCategory.NETWORK


class TLSError(NetworkConnectionError):
    """The secure connection failed, for example because the certificate is not trusted."""

    error_code: ClassVar[str] = "TLS_FAILED"
    category: ClassVar[ErrorCategory] = ErrorCategory.TLS

    _retryable_default = False


class InvalidResponseError(NetworkError):
    """The server answered, but not with what was asked for (a web page, nothing, too little)."""

    error_code: ClassVar[str] = "RESPONSE_INVALID"
    category: ClassVar[ErrorCategory] = ErrorCategory.NETWORK


class HTTPError(NetworkError):
    """The server answered with an error status."""

    error_code: ClassVar[str] = "HTTP_ERROR"
    category: ClassVar[ErrorCategory] = ErrorCategory.HTTP

    def __init__(
        self,
        url: str,
        status_code: int,
        *,
        hint: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        self.url = redact_url(url)
        self.status_code = status_code
        #: Seconds the server asked us to wait before trying again, when it said so.
        self.retry_after = retry_after
        super().__init__(f"HTTP {status_code} for {self.url}", hint=hint)

    @property
    def code(self) -> str:
        """``HTTP_`` and the status, for example ``HTTP_503``."""
        return f"HTTP_{self.status_code}"

    @property
    def retryable(self) -> bool:
        """Whether trying the same request again could succeed."""
        return self.status_code in {408, 425, 429} or self.status_code >= 500


class AuthenticationError(HTTPError):
    """The server refused the credentials, or wants some (HTTP 401 or 403)."""

    error_code: ClassVar[str] = "AUTH_REQUIRED"
    category: ClassVar[ErrorCategory] = ErrorCategory.AUTHENTICATION

    @property
    def code(self) -> str:
        """``AUTH_`` and the status, for example ``AUTH_403``."""
        return f"AUTH_{self.status_code}"


class DownloadError(RayoHXError):
    """The download failed."""

    error_code: ClassVar[str] = "DOWNLOAD_FAILED"
    category: ClassVar[ErrorCategory] = ErrorCategory.SEGMENT


class SegmentDownloadError(DownloadError):
    """A single segment could not be downloaded."""

    error_code: ClassVar[str] = "SEGMENT_FAILED"
    category: ClassVar[ErrorCategory] = ErrorCategory.SEGMENT

    def __init__(self, index: int, url: str, reason: str, *, hint: str | None = None) -> None:
        self.index = index
        self.url = redact_url(url)
        super().__init__(f"Segment {index} failed ({reason}): {self.url}", hint=hint)


class DecryptionError(DownloadError):
    """A segment could not be decrypted, usually because the key is wrong."""

    error_code: ClassVar[str] = "DECRYPTION_FAILED"
    category: ClassVar[ErrorCategory] = ErrorCategory.CRYPTO


class WorkspaceLockedError(DownloadError):
    """Another download is already using this working folder."""

    error_code: ClassVar[str] = "WORKSPACE_LOCKED"
    category: ClassVar[ErrorCategory] = ErrorCategory.STORAGE


class InvalidStateTransitionError(DownloadError):
    """A download was asked to move to a state it cannot reach from where it is."""

    error_code: ClassVar[str] = "STATE_INVALID"
    category: ClassVar[ErrorCategory] = ErrorCategory.INTERNAL


class OutputError(RayoHXError):
    """The output could not be produced."""

    error_code: ClassVar[str] = "OUTPUT_ERROR"
    category: ClassVar[ErrorCategory] = ErrorCategory.OUTPUT


class InsufficientStorageError(OutputError):
    """There is not enough free disk space for the chosen storage strategy."""

    error_code: ClassVar[str] = "STORAGE_LOW"
    category: ClassVar[ErrorCategory] = ErrorCategory.STORAGE

    def __init__(self, required_bytes: int, available_bytes: int, *, location: str) -> None:
        self.required_bytes = required_bytes
        self.available_bytes = available_bytes
        super().__init__(
            f"Not enough disk space in {location}: need {format_bytes(required_bytes)}, "
            f"{format_bytes(available_bytes)} available.",
            hint="Free some space, pick another folder, or choose a storage strategy that "
            "uses less working space.",
        )


class OutputExistsError(OutputError):
    """The output file already exists and overwriting was not requested."""

    error_code: ClassVar[str] = "OUTPUT_EXISTS"
    category: ClassVar[ErrorCategory] = ErrorCategory.OUTPUT


class OutputFormatError(OutputError):
    """The stream cannot be written in the requested format."""

    error_code: ClassVar[str] = "OUTPUT_FORMAT"
    category: ClassVar[ErrorCategory] = ErrorCategory.OUTPUT


class UnsupportedCodecError(OutputFormatError):
    """The stream uses a codec the built-in remuxer cannot copy into an MP4 file."""

    error_code: ClassVar[str] = "CODEC_UNSUPPORTED"
    category: ClassVar[ErrorCategory] = ErrorCategory.REMUX

    def __init__(self, codec: str, *, hint: str | None = None) -> None:
        self.codec = codec
        super().__init__(
            f"The stream uses {codec}, which the built-in remuxer does not support.",
            hint=hint or "FFmpeg, if installed, can handle this stream.",
        )


class FinalizationError(OutputError):
    """Joining or validating the downloaded data failed."""

    error_code: ClassVar[str] = "FINALIZATION_FAILED"
    category: ClassVar[ErrorCategory] = ErrorCategory.OUTPUT


class CancellationError(RayoHXError):
    """The download was cancelled."""

    error_code: ClassVar[str] = "CANCELLED"
    category: ClassVar[ErrorCategory] = ErrorCategory.CANCELLATION
