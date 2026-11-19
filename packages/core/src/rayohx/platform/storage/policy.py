"""What to do as the disk fills up."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, Any

from rayohx.errors import ConfigurationError
from rayohx.platform.storage.sizes import format_size, parse_size

if TYPE_CHECKING:
    from rayohx.platform.persistence import SettingsStore

SETTINGS_KEY = "storage.policy"


class StorageLevel(IntEnum):
    """How little room is left. Higher is worse."""

    OK = 0
    #: Below the warning threshold: tell someone, carry on.
    LOW = 1
    #: Below the pause threshold: running downloads wait, nothing new starts.
    PAUSE = 2
    #: Below the stop threshold: running downloads are stopped (and can be retried later).
    STOP = 3


@dataclass(frozen=True, slots=True, kw_only=True)
class StoragePolicy:
    """Free-space thresholds, in bytes, for the disk downloads are saved on.

    Each is optional; with none set the queue only counts and reports. They must be in order:
    ``warn_below`` >= ``pause_below`` >= ``stop_below``.
    """

    warn_below: int | None = None
    pause_below: int | None = None
    stop_below: int | None = None
    #: Prefer ways of downloading that keep little working data, even when there is room.
    low_storage_mode: bool = False
    #: Paused downloads resume when free space is this much above the pause threshold.
    resume_margin: float = 0.1

    def __post_init__(self) -> None:
        for name in ("warn_below", "pause_below", "stop_below"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ConfigurationError(f"{name} must not be negative.")
        ordered = [v for v in (self.warn_below, self.pause_below, self.stop_below) if v is not None]
        if ordered != sorted(ordered, reverse=True):
            raise ConfigurationError(
                "The thresholds are out of order.",
                hint="Warn first (the most free space), then pause, then stop (the least).",
            )
        if not 0 <= self.resume_margin <= 1:
            raise ConfigurationError("resume_margin must be between 0 and 1.")

    @property
    def active(self) -> bool:
        return any(v is not None for v in (self.warn_below, self.pause_below, self.stop_below))

    def level_for(self, free: int, *, current: StorageLevel = StorageLevel.OK) -> StorageLevel:
        """The level free space ``free`` means, with a margin before easing back from ``current``.

        Getting worse is immediate; getting better needs ``resume_margin`` more room than the
        threshold that was crossed, so the queue does not flap around a threshold.
        """
        raw = StorageLevel.OK
        for level, limit in (
            (StorageLevel.STOP, self.stop_below),
            (StorageLevel.PAUSE, self.pause_below),
            (StorageLevel.LOW, self.warn_below),
        ):
            if limit is not None and free < limit:
                raw = level
                break
        if raw >= current:
            return raw
        limit = {
            StorageLevel.STOP: self.stop_below,
            StorageLevel.PAUSE: self.pause_below,
            StorageLevel.LOW: self.warn_below,
        }[current]
        if limit is not None and free < limit * (1 + self.resume_margin):
            return current
        return raw

    def to_dict(self) -> dict[str, Any]:
        return {
            "warn_below": self.warn_below,
            "pause_below": self.pause_below,
            "stop_below": self.stop_below,
            "low_storage_mode": self.low_storage_mode,
            "resume_margin": self.resume_margin,
        }

    def describe(self) -> str:
        parts = [
            f"{name} below {format_size(value)}"
            for name, value in (
                ("warn", self.warn_below),
                ("pause", self.pause_below),
                ("stop", self.stop_below),
            )
            if value is not None
        ]
        text = ", ".join(parts) or "no thresholds"
        return text + (", low-storage mode on" if self.low_storage_mode else "")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoragePolicy:
        def size(name: str) -> int | None:
            value = data.get(name)
            return None if value in (None, "") else parse_size(value, what=name)

        return cls(
            warn_below=size("warn_below"),
            pause_below=size("pause_below"),
            stop_below=size("stop_below"),
            low_storage_mode=bool(data.get("low_storage_mode", False)),
            resume_margin=float(data.get("resume_margin", 0.1)),
        )


def load_policy(settings: SettingsStore) -> StoragePolicy:
    try:
        return StoragePolicy.from_dict(settings.get(SETTINGS_KEY) or {})
    except ConfigurationError:
        return StoragePolicy()  # a hand-edited bad value must not stop the queue


def save_policy(settings: SettingsStore, policy: StoragePolicy) -> None:
    settings.set(SETTINGS_KEY, policy.to_dict())
