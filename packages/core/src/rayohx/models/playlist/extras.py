"""Descriptive tags of a playlist: session data and date ranges."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionData:
    """One ``EXT-X-SESSION-DATA`` tag: a named piece of information about the whole stream."""

    data_id: str
    value: str | None = None
    uri: str | None = None
    language: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class DateRange:
    """One ``EXT-X-DATERANGE`` tag: something that happens between two moments."""

    id: str
    start: datetime
    end: datetime | None = None
    duration: float | None = None
    kind: str | None = None
    #: The tag's other attributes, such as ``X-TITLE``.
    attributes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))
