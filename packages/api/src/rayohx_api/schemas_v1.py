"""Request and response models for ``/api/v1``."""

from typing import Any, Literal

from pydantic import BaseModel, Field

QUALITY = r"(?i)^(best|worst|auto|\d{3,4}p)$"


class Network(BaseModel):
    """Optional request settings applied when fetching the playlist."""

    headers: dict[str, str] = Field(default_factory=dict, max_length=32)


class InspectRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096, description="Address of an HLS playlist.")
    quality: str = Field(default="best", pattern=QUALITY)
    network: Network = Field(default_factory=Network)


class InspectResponse(BaseModel):
    """A master or media playlist as plain data (see ``rayohx.serialization``)."""

    playlist: dict[str, Any]


class DownloadCreate(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    filename: str | None = Field(
        default=None,
        max_length=200,
        description="File name inside the download folder. Folders are not accepted.",
    )
    quality: str = Field(default="best", pattern=QUALITY)
    audio: list[str] = Field(default_factory=list, max_length=16)
    subtitles: list[str] = Field(default_factory=list, max_length=16)
    video_only: bool = False
    format: Literal["auto", "mp4", "mkv", "ts"] = "auto"
    overwrite: bool = False
    network: Network = Field(default_factory=Network)


class Progress(BaseModel):
    state: str
    downloaded_bytes: int = 0
    written_bytes: int = 0
    total_bytes: int | None = None
    completed_segments: int = 0
    total_segments: int | None = None
    fraction: float | None = None
    speed: float = 0.0
    average_speed: float = 0.0
    eta_seconds: float | None = None
    active_workers: int = 0


class Job(BaseModel):
    id: str
    url: str = Field(description="The address with any signing token removed.")
    state: str
    created_at: float
    updated_at: float
    progress: Progress | None = None
    output_path: str | None = None
    output_size_bytes: int | None = None
    error: str | None = None


class JobList(BaseModel):
    items: list[Job]


class SettingsView(BaseModel):
    download_dir: str
    max_active_downloads: int
    concurrency: int = Field(ge=1, le=64)
    quality: str = Field(default="best", pattern=QUALITY)
    overwrite: bool = False
    version: str


class SettingsUpdate(BaseModel):
    concurrency: int | None = Field(default=None, ge=1, le=64)
    quality: str | None = Field(default=None, pattern=QUALITY)
    overwrite: bool | None = None


class CleanRequest(BaseModel):
    older_than_days: float = Field(default=0, ge=0)
    dry_run: bool = True


class CleanedFolder(BaseModel):
    name: str
    size_bytes: int
    age_days: float


class CleanResponse(BaseModel):
    dry_run: bool
    folders: list[CleanedFolder]
    freed_bytes: int
    skipped_in_use: int
