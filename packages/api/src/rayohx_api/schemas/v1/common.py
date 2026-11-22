"""Models and patterns shared by the ``/api/v1`` schemas."""

from pydantic import BaseModel, Field

QUALITY = r"(?i)^(best|worst|auto|\d{3,4}p)$"


class Network(BaseModel):
    """Optional request settings applied when fetching the playlist."""

    headers: dict[str, str] = Field(default_factory=dict, max_length=32)
