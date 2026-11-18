"""Jobs: what the queue stores and reports."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from rayohx.enums import DownloadState
from rayohx.platform.jobs.retry import RetryPolicy

if TYPE_CHECKING:
    from collections.abc import Mapping


class JobState(StrEnum):
    """Where a queued job is."""

    QUEUED = "queued"
    PREPARING = "preparing"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    FINALIZING = "finalizing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}

    @property
    def is_active(self) -> bool:
        """Whether a runner is working on the job."""
        return self in ACTIVE_STATES


ACTIVE_STATES = frozenset(
    {JobState.PREPARING, JobState.DOWNLOADING, JobState.FINALIZING, JobState.VERIFYING}
)

#: How the engine's states appear on a job. Terminal engine states are decided by the runner.
ENGINE_STATE_TO_JOB: Mapping[DownloadState, JobState] = MappingProxyType(
    {
        DownloadState.QUEUED: JobState.PREPARING,
        DownloadState.INSPECTING: JobState.PREPARING,
        DownloadState.PREPARING: JobState.PREPARING,
        DownloadState.DOWNLOADING: JobState.DOWNLOADING,
        DownloadState.PAUSED: JobState.DOWNLOADING,
        DownloadState.FINALIZING: JobState.FINALIZING,
        DownloadState.VERIFYING: JobState.VERIFYING,
    }
)


class QueuePriority(IntEnum):
    """Higher runs first."""

    LOW = 0
    NORMAL = 1
    HIGH = 2

    @classmethod
    def parse(cls, value: str | int | QueuePriority) -> QueuePriority:
        if isinstance(value, str):
            try:
                return cls[value.strip().upper()]
            except KeyError:
                raise ValueError(f"unknown priority {value!r}; use low, normal or high") from None
        return cls(value)


class VerificationState(StrEnum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    FAILED = "failed"


@dataclass(frozen=True, slots=True, kw_only=True)
class JobSpec:
    """Everything needed to run a job again after a restart, apart from its secrets."""

    url: str
    options: Mapping[str, Any]
    playlist_text: str | None = None
    #: A plain file name inside the output folder. ``None`` names the file after the address.
    output_name: str | None = None
    retry: RetryPolicy = field(default_factory=RetryPolicy)

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", MappingProxyType(dict(self.options)))

    def to_json(self) -> str:
        return json.dumps(
            {
                "url": self.url,
                "options": dict(self.options),
                "playlist_text": self.playlist_text,
                "output_name": self.output_name,
                "retry": self.retry.to_dict(),
            },
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, text: str) -> JobSpec:
        data = json.loads(text)
        return cls(
            url=data["url"],
            options=data["options"],
            playlist_text=data.get("playlist_text"),
            output_name=data.get("output_name"),
            retry=RetryPolicy.from_dict(data.get("retry") or {}),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class JobRecord:
    """A queued job as stored. ``url`` is safe to show; the real address is in ``spec``."""

    id: str
    url: str
    spec: JobSpec = field(repr=False)
    state: JobState
    priority: QueuePriority
    rank: float
    attempts: int
    verification: VerificationState
    created_at: float
    updated_at: float
    started_at: float | None = None
    finished_at: float | None = None
    error_code: str | None = None
    error_message: str | None = None
    output_path: str | None = None
    output_size: int | None = None
    not_before: float | None = None
    recovered: bool = False
    needs_credentials: bool = False
    control_request: str | None = None
    #: The latest progress snapshot (live while the job runs in this process).
    progress: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Plain data for the API and the command line. Never includes the real address."""
        return {
            "id": self.id,
            "url": self.url,
            "state": self.state.value,
            "priority": self.priority.name.lower(),
            "rank": self.rank,
            "attempts": self.attempts,
            "max_attempts": self.spec.retry.max_attempts,
            "verification": self.verification.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error_code": self.error_code,
            "error": self.error_message,
            "output_path": self.output_path,
            "output_size_bytes": self.output_size,
            "not_before": self.not_before,
            "recovered": self.recovered,
            "needs_credentials": self.needs_credentials,
            "progress": dict(self.progress) if self.progress else None,
        }


@dataclass(slots=True)
class BulkResult:
    """What a bulk action did to each job."""

    done: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failed

    def to_dict(self) -> dict[str, Any]:
        return {"done": list(self.done), "failed": dict(self.failed)}
