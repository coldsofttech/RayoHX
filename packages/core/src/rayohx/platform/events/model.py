"""The platform event: one record of something that happened, for every consumer to share."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from pathlib import PurePath
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from rayohx.redaction import REDACTED, is_sensitive_name, redact_text

if TYPE_CHECKING:
    from collections.abc import Mapping


class EventCategory(StrEnum):
    """Which part of the platform an event belongs to."""

    SYSTEM = "system"
    QUEUE = "queue"
    DOWNLOAD = "download"
    VERIFICATION = "verification"
    AUTOMATION = "automation"
    SCHEDULING = "scheduling"
    STORAGE = "storage"
    DIAGNOSTICS = "diagnostics"
    NOTIFICATION = "notification"
    BROWSER = "browser"
    PLUGIN = "plugin"


class Severity(IntEnum):
    """How much attention an event deserves. Ordered, so ``>=`` filters work."""

    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40


_MAX_DEPTH = 8
_MAX_TEXT = 4000


def sanitize(value: Any, _depth: int = 0) -> Any:
    """Turn ``value`` into plain JSON data with secrets removed.

    Values under a sensitive name (``token``, ``password``, ``authorization``, ...) are replaced,
    text is redacted, and anything that is not plain data is shown as text. This runs on every
    event, so a secret cannot reach the database, a log or a notification through a payload.
    """
    if _depth > _MAX_DEPTH:
        return "..."
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        text = redact_text(value)
        return text if len(text) <= _MAX_TEXT else text[:_MAX_TEXT] + "..."
    if isinstance(value, bytes | bytearray):
        return f"<{len(value)} bytes>"
    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, dict | MappingProxyType) or hasattr(value, "items"):
        return {
            str(key): REDACTED if is_sensitive_name(str(key)) else sanitize(item, _depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple | set | frozenset):
        return [sanitize(item, _depth + 1) for item in value]
    inner = getattr(value, "value", None)
    if isinstance(inner, str | int):
        return inner
    return sanitize(str(value), _depth + 1)


@dataclass(frozen=True, slots=True, kw_only=True)
class PlatformEvent:
    """Something that happened. Immutable; the payload is sanitized on creation."""

    #: Dotted name, for example ``queue.job_added`` or ``download.segment_failed``.
    type: str
    category: EventCategory = EventCategory.SYSTEM
    severity: Severity = Severity.INFO
    timestamp: float = field(default_factory=time.time)
    job_id: str | None = None
    #: Ties together events that belong to one action, such as a workflow run.
    correlation_id: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    #: Assigned by the store; ``None`` until the event is saved.
    id: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(sanitize(dict(self.payload))))

    def to_dict(self) -> dict[str, Any]:
        """Plain JSON data, for the API, logs and notifications."""
        return {
            "id": self.id,
            "type": self.type,
            "category": self.category.value,
            "severity": self.severity.name.lower(),
            "timestamp": self.timestamp,
            "job_id": self.job_id,
            "correlation_id": self.correlation_id,
            "payload": dict(self.payload),
        }
