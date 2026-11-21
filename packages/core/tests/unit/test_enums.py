"""Tests for the shared enumerations."""

from __future__ import annotations

from enum import StrEnum

import pytest

from rayohx.enums import (
    ContainerFormat,
    DownloadState,
    EncryptionMethod,
    EventType,
    OutputFormat,
    RemuxBackend,
    SegmentState,
    StorageStrategy,
)

ALL_ENUMS = [
    DownloadState,
    SegmentState,
    EventType,
    ContainerFormat,
    EncryptionMethod,
    StorageStrategy,
    OutputFormat,
    RemuxBackend,
]


@pytest.mark.parametrize("enum", ALL_ENUMS)
def test_is_str_enum_with_unique_values(enum: type[StrEnum]) -> None:
    values = [member.value for member in enum]
    assert issubclass(enum, StrEnum)
    assert len(values) == len(set(values))


@pytest.mark.parametrize("enum", ALL_ENUMS)
def test_members_compare_and_round_trip_as_strings(enum: type[StrEnum]) -> None:
    for member in enum:
        assert member == member.value
        assert str(member) == member.value
        assert enum(member.value) is member


@pytest.mark.parametrize("enum", ALL_ENUMS)
def test_unknown_value_is_rejected(enum: type[StrEnum]) -> None:
    with pytest.raises(ValueError, match="not-a-real-value"):
        enum("not-a-real-value")


@pytest.mark.parametrize(
    ("enum", "expected"),
    [
        (
            DownloadState,
            {
                "queued",
                "inspecting",
                "preparing",
                "downloading",
                "finalizing",
                "completed",
                "failed",
                "cancelled",
                "paused",
            },
        ),
        (SegmentState, {"pending", "downloading", "completed", "failed", "skipped"}),
        (ContainerFormat, {"mpeg-ts", "fmp4", "webvtt", "unknown"}),
        (EncryptionMethod, {"NONE", "AES-128", "SAMPLE-AES"}),
        (
            StorageStrategy,
            {"auto", "direct", "streaming", "buffered", "temporary", "hybrid"},
        ),
        (OutputFormat, {"auto", "ts", "mp4", "segments"}),
        (RemuxBackend, {"auto", "native", "ffmpeg"}),
    ],
)
def test_wire_values_are_stable(enum: type[StrEnum], expected: set[str]) -> None:
    assert {member.value for member in enum} == expected


def test_event_type_values_are_stable() -> None:
    assert {member.value for member in EventType} == {
        "download_started",
        "playlist_loaded",
        "stream_selected",
        "segment_started",
        "segment_completed",
        "segment_failed",
        "download_progress",
        "finalization_started",
        "finalization_completed",
        "download_completed",
        "download_failed",
        "download_cancelled",
        "download_paused",
        "download_resumed",
    }


@pytest.mark.parametrize(
    "state",
    [DownloadState.COMPLETED, DownloadState.FAILED, DownloadState.CANCELLED],
)
def test_terminal_download_states(state: DownloadState) -> None:
    assert state.is_terminal is True


@pytest.mark.parametrize(
    "state",
    [
        DownloadState.QUEUED,
        DownloadState.INSPECTING,
        DownloadState.PREPARING,
        DownloadState.DOWNLOADING,
        DownloadState.FINALIZING,
        DownloadState.PAUSED,
    ],
)
def test_non_terminal_download_states(state: DownloadState) -> None:
    assert state.is_terminal is False
