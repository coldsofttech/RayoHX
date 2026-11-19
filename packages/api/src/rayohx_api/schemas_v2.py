"""Request and response models for ``/api/v2``."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from rayohx_api.schemas_v1 import DownloadCreate, Job, Network, Selection

Priority = Literal["low", "normal", "high"]


class Retry(BaseModel):
    """When a failed job is run again."""

    max_attempts: int = Field(default=3, ge=1, le=20, description="Runs in total; 1 means never.")
    initial_delay: float = Field(default=10, ge=0, le=86400, description="Seconds.")
    factor: float = Field(default=2, ge=1, le=10)
    max_delay: float = Field(default=600, ge=0, le=86400, description="Seconds.")


class VerifyOptions(BaseModel):
    """How the finished file is checked."""

    level: Literal["none", "basic", "strong"] | None = Field(
        default=None, description="Default: the profile's, else basic."
    )
    checksum: str | None = Field(
        default=None,
        max_length=128,
        pattern=r"^[0-9a-fA-F]+$",
        description="The checksum the file must have (md5, sha1, sha256 or sha512, by length).",
    )


class MetadataOptions(BaseModel):
    """What is written into the file."""

    policy: Literal["none", "minimal", "preserve", "custom"] | None = Field(
        default=None, description="Default: the profile's, else preserve."
    )
    title: str | None = Field(default=None, max_length=500, description="Replaces the stream's.")
    description: str | None = Field(default=None, max_length=2000)
    language: str | None = Field(default=None, max_length=35)
    artwork: bool | None = None
    chapters: bool | None = None


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
    verify: VerifyOptions = Field(default_factory=VerifyOptions)
    metadata: MetadataOptions = Field(default_factory=MetadataOptions)
    name_template: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "Name the file from the stream: {name} {title} {language} {date} {time} {host}."
        ),
    )


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
    notes: list[str] = Field(description="Things worth knowing, such as metadata not written.")


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


class CheckOut(BaseModel):
    name: str
    status: Literal["passed", "failed", "skipped"]
    detail: str


class VerificationOut(BaseModel):
    """How a finished download was checked, and everything that could not be."""

    status: Literal["not_requested", "pending", "verifying", "verified", "failed"]
    level: Literal["none", "basic", "strong"]
    checks: list[CheckOut]
    segments_checked: int
    checksum: dict[str, Any] | None = None
    media: dict[str, Any] | None = Field(default=None, description="What ffprobe found.")
    elapsed_seconds: float
    invalid_path: str | None = Field(
        default=None, description="Where a file that failed was kept, if it was."
    )
    notes: list[str]


class MediaInfoRequest(BaseModel):
    url: str | None = Field(default=None, max_length=4096)
    playlist_text: str | None = Field(default=None, max_length=1_000_000)
    base_url: str | None = Field(default=None, max_length=4096)
    network: Network = Field(default_factory=Network)
    selection: Selection = Field(default_factory=Selection)
    probe: bool = Field(default=True, description="Also examine the first segment (needs ffprobe).")
    format: Literal["auto", "original", "ts", "mp4", "mkv", "audio", "segments"] = Field(
        default="auto", description="Say whether the stream can be saved in this format."
    )


class CompatibilityOut(BaseModel):
    level: Literal["error", "warning", "info"]
    message: str


class MediaInfoResponse(BaseModel):
    media: dict[str, Any]
    compatibility: list[CompatibilityOut]


class StoragePolicyBody(BaseModel):
    """Free-space thresholds for the downloads disk. Sizes are bytes or text such as ``5GB``."""

    warn_below: str | int | None = Field(default=None, description="Warn under this much free.")
    pause_below: str | int | None = Field(default=None, description="Pause downloads under this.")
    stop_below: str | int | None = Field(default=None, description="Stop downloads under this.")
    low_storage_mode: bool = Field(default=False, description="Prefer ways that keep little data.")
    resume_margin: float = Field(default=0.1, ge=0, le=1)


class CleanupRequest(BaseModel):
    """What to clean. Downloaded files are never touched."""

    dry_run: bool = Field(default=True, description="Only list what would be removed.")
    older_than_days: float = Field(default=7, ge=0, le=3650)
    report_days: float | None = Field(default=30, ge=0, le=3650)


class NetworkCheckRequest(BaseModel):
    """Check reaching a server, with a job's headers and proxy or just the defaults."""

    url: str | None = Field(default=None, max_length=4096)
    job_id: str | None = Field(default=None, max_length=64)
    network: Network | None = None
    timeout: float = Field(default=10, ge=1, le=60)


class ReportRequest(BaseModel):
    """A sanitized report, optionally including checks of one address."""

    job_id: str | None = Field(default=None, max_length=64)
    url: str | None = Field(default=None, max_length=4096)
    include_network: bool = False
    include_stream: bool = False
    save: bool = True
