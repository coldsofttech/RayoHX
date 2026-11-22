"""Models for reading and changing the defaults."""

from pydantic import BaseModel, Field
from rayohx.config.download import MAX_CONCURRENCY

from rayohx_api.schemas.v1.common import MIN_CONCURRENCY, QUALITY


class Limits(BaseModel):
    """What the engine accepts, so a client can offer only valid choices."""

    min_concurrency: int = Field(description="Fewest parallel segments.")
    max_concurrency: int = Field(description="Most parallel segments.")


class SettingsView(BaseModel):
    download_dir: str
    max_active_downloads: int
    allow_local_paths: bool
    concurrency: int = Field(ge=MIN_CONCURRENCY, le=MAX_CONCURRENCY)
    quality: str = Field(default="best", pattern=QUALITY)
    overwrite: bool = False
    limits: Limits
    version: str


class SettingsUpdate(BaseModel):
    concurrency: int | None = Field(default=None, ge=MIN_CONCURRENCY, le=MAX_CONCURRENCY)
    quality: str | None = Field(default=None, pattern=QUALITY)
    overwrite: bool | None = None
