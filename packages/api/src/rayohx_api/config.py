"""Settings, read from ``RAYOHX_API_*`` environment variables or a ``.env`` file."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthMode(StrEnum):
    """How requests to protected routes are authenticated."""

    NONE = "none"
    API_KEY = "api_key"


class Settings(BaseSettings):
    """Application settings. List values are given as JSON, for example ``["a", "b"]``."""

    model_config = SettingsConfigDict(env_prefix="RAYOHX_API_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    docs_enabled: bool = False
    max_body_bytes: int = Field(default=1_048_576, ge=1)
    cors_origins: list[str] = []
    #: Folder downloads are saved in. Clients choose file names, never folders.
    download_dir: Path = Path.home() / "Downloads" / "RayoHX"
    #: Folder for the queue database and other platform data. Empty means the per-user folders.
    home: Path | None = None
    #: Where default options are saved between runs. Empty means the per-user config folder.
    defaults_file: Path | None = None
    #: Let requests name files on this machine (cookie files, certificates, FFmpeg, file keys).
    #: Off for a network service, because a client could then make the server read its own files.
    #: The desktop window turns it on, since there the client is you.
    allow_local_paths: bool = False
    #: Downloads that run at once; the rest wait in the queue.
    max_active_downloads: int = Field(default=2, ge=1, le=16)

    auth_mode: AuthMode = AuthMode.API_KEY
    api_keys: list[SecretStr] = []

    def check_auth(self) -> Self:
        """Fail at startup, not on the first request, if authentication is misconfigured."""
        if self.auth_mode is AuthMode.API_KEY and not self.api_keys:
            raise ValueError(
                "RAYOHX_API_API_KEYS is required; "
                "set RAYOHX_API_AUTH_MODE=none to disable authentication for local development"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the settings, read once per process."""
    return Settings()
