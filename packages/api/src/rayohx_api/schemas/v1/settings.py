"""Models for reading and changing the defaults."""

from pydantic import BaseModel, Field

from rayohx_api.schemas.v1.common import QUALITY


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
