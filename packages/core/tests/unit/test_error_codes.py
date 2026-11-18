"""Every error has a stable code and category; reports and exit codes depend on them."""

import inspect

import pytest

from rayohx import errors
from rayohx.enums import ErrorCategory
from rayohx.errors import (
    AuthenticationError,
    HTTPError,
    InsufficientStorageError,
    RayoHXError,
)

EXPECTED = {
    "ConfigurationError": ("CONFIGURATION_INVALID", ErrorCategory.CONFIGURATION),
    "PlaylistError": ("PLAYLIST_ERROR", ErrorCategory.PLAYLIST),
    "InvalidPlaylistError": ("PLAYLIST_INVALID", ErrorCategory.PLAYLIST),
    "UnsupportedPlaylistError": ("PLAYLIST_UNSUPPORTED", ErrorCategory.PLAYLIST),
    "PlaylistNotFoundError": ("PLAYLIST_NOT_FOUND", ErrorCategory.PLAYLIST),
    "NetworkError": ("NETWORK_ERROR", ErrorCategory.NETWORK),
    "NetworkConnectionError": ("NETWORK_CONNECTION", ErrorCategory.NETWORK),
    "NetworkTimeoutError": ("NETWORK_TIMEOUT", ErrorCategory.NETWORK),
    "TLSError": ("TLS_FAILED", ErrorCategory.TLS),
    "InvalidResponseError": ("RESPONSE_INVALID", ErrorCategory.NETWORK),
    "HTTPError": ("HTTP_ERROR", ErrorCategory.HTTP),
    "AuthenticationError": ("AUTH_REQUIRED", ErrorCategory.AUTHENTICATION),
    "DownloadError": ("DOWNLOAD_FAILED", ErrorCategory.SEGMENT),
    "SegmentDownloadError": ("SEGMENT_FAILED", ErrorCategory.SEGMENT),
    "DecryptionError": ("DECRYPTION_FAILED", ErrorCategory.CRYPTO),
    "WorkspaceLockedError": ("WORKSPACE_LOCKED", ErrorCategory.STORAGE),
    "InvalidStateTransitionError": ("STATE_INVALID", ErrorCategory.INTERNAL),
    "OutputError": ("OUTPUT_ERROR", ErrorCategory.OUTPUT),
    "InsufficientStorageError": ("STORAGE_LOW", ErrorCategory.STORAGE),
    "OutputExistsError": ("OUTPUT_EXISTS", ErrorCategory.OUTPUT),
    "OutputFormatError": ("OUTPUT_FORMAT", ErrorCategory.OUTPUT),
    "UnsupportedCodecError": ("CODEC_UNSUPPORTED", ErrorCategory.REMUX),
    "FinalizationError": ("FINALIZATION_FAILED", ErrorCategory.OUTPUT),
    "CancellationError": ("CANCELLED", ErrorCategory.CANCELLATION),
    "VerificationError": ("VERIFICATION_FAILED", ErrorCategory.VERIFICATION),
}


def error_classes() -> dict[str, type[RayoHXError]]:
    return {
        name: cls
        for name, cls in inspect.getmembers(errors, inspect.isclass)
        if issubclass(cls, RayoHXError) and cls is not RayoHXError
    }


def test_every_error_class_is_in_the_table() -> None:
    assert set(error_classes()) == set(EXPECTED)


@pytest.mark.parametrize(("name", "expected"), sorted(EXPECTED.items()))
def test_each_error_keeps_its_code_and_category(
    name: str, expected: tuple[str, ErrorCategory]
) -> None:
    cls = error_classes()[name]
    assert (cls.error_code, cls.category) == expected


def test_codes_are_unique() -> None:
    codes = [code for code, _ in EXPECTED.values()]
    assert len(codes) == len(set(codes))


def test_http_errors_carry_their_status_in_the_code() -> None:
    assert HTTPError("https://x.test/a", 503).code == "HTTP_503"
    assert AuthenticationError("https://x.test/a", 403).code == "AUTH_403"


def test_other_errors_use_the_class_code() -> None:
    assert InsufficientStorageError(10, 1, location="the output folder").code == "STORAGE_LOW"
