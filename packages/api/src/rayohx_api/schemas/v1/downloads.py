"""Models for starting, listing and following downloads."""

from typing import Literal

from pydantic import BaseModel, Field

from rayohx_api.schemas.v1.common import QUALITY, Network


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
