"""Models for looking at a playlist."""

from typing import Any

from pydantic import BaseModel, Field

from rayohx_api.schemas.v1.common import QUALITY, Network


class InspectRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096, description="Address of an HLS playlist.")
    quality: str = Field(default="best", pattern=QUALITY)
    network: Network = Field(default_factory=Network)


class InspectResponse(BaseModel):
    """A master or media playlist as plain data (see ``rayohx.serialization``)."""

    playlist: dict[str, Any]
