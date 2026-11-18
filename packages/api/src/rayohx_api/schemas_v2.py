"""Request and response models for ``/api/v2``."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from rayohx_api.schemas_v1 import DownloadCreate, Job

Priority = Literal["low", "normal", "high"]


class Retry(BaseModel):
    """When a failed job is run again."""

    max_attempts: int = Field(default=3, ge=1, le=20, description="Runs in total; 1 means never.")
    initial_delay: float = Field(default=10, ge=0, le=86400, description="Seconds.")
    factor: float = Field(default=2, ge=1, le=10)
    max_delay: float = Field(default=600, ge=0, le=86400, description="Seconds.")


class QueueAdd(DownloadCreate):
    profile: str | None = Field(
        default=None,
        max_length=80,
        description=(
            "A profile's id or name. Its settings apply, and only the options you set in this "
            "request override them. Without it, the default profile (if any) is used."
        ),
    )
    priority: Priority = "normal"
    retry: Retry = Field(default_factory=Retry)


class QueueJob(Job):
    profile: str | None = Field(
        default=None, description="The profile the job's settings came from."
    )
    priority: Priority
    rank: float
    attempts: int
    max_attempts: int
    verification: str
    error_code: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    not_before: float | None = Field(default=None, description="A retry waits until this time.")
    recovered: bool = Field(description="Found half way after a crash and put back in the queue.")
    needs_credentials: bool = Field(description="Its secrets were lost; supply them to go on.")


class QueueStats(BaseModel):
    counts: dict[str, int]
    total: int
    active: int
    max_active: int
    runner: Literal["this process", "another process", "none"]


class QueueList(BaseModel):
    items: list[QueueJob]
    stats: QueueStats


class QueueAction(BaseModel):
    action: Literal["pause", "resume", "cancel", "retry", "remove", "priority", "top", "bottom"]
    ids: list[str] = Field(min_length=1, max_length=500)
    priority: Priority | None = Field(default=None, description="Needed for the priority action.")


class BulkOutcome(BaseModel):
    done: list[str]
    failed: dict[str, str] = Field(description="Job id to the reason it was not changed.")


class MoveRequest(BaseModel):
    before: str = Field(description="Put the job just before this one.")


class QueueSettings(BaseModel):
    max_active: int = Field(ge=1, le=16, description="Jobs that run at once.")


class Attempt(BaseModel):
    attempt: int
    started_at: float
    finished_at: float | None = None
    outcome: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class JobDetail(QueueJob):
    attempt_history: list[Attempt]


class PlatformEvent(BaseModel):
    id: int
    type: str
    category: str
    severity: str
    timestamp: float
    job_id: str | None = None
    correlation_id: str | None = None
    payload: dict[str, Any]


class EventList(BaseModel):
    items: list[PlatformEvent]
    last_id: int = Field(description="Pass as after_id to get only newer events.")


class ProfileOut(BaseModel):
    id: str
    name: str
    description: str
    builtin: bool
    default: bool
    options: dict[str, Any] = Field(description="Only the settings the profile changes.")
    max_attempts: int | None = Field(default=None, description="Its retry policy, if it has one.")
    naming: str | None = None
    metadata: str
    verify: str
    problems: list[str] = Field(description="Why this server cannot use it now, if it cannot.")


class ProfileList(BaseModel):
    items: list[ProfileOut]


class CapabilitiesOut(BaseModel):
    ffmpeg: str | None = Field(description="Where FFmpeg was found, if it was.")
    ffprobe: str | None = None
    formats: dict[str, bool] = Field(
        description="Output format to whether this server can make it."
    )
