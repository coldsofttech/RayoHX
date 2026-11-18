"""The outcome of checking a finished download."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from rayohx.enums import VerificationStatus, VerifyLevel

if TYPE_CHECKING:
    from rayohx.media.probe import FileInfo


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    #: Could not be done here (for example ffprobe is missing). Never counts as a failure.
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class Check:
    """One thing that was looked at."""

    name: str
    status: CheckStatus
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status.value, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class ChecksumResult:
    """A checksum of the finished file."""

    algorithm: str
    value: str
    expected: str | None = None

    @property
    def matches(self) -> bool | None:
        """Whether it equals the expected checksum; ``None`` if none was expected."""
        return None if self.expected is None else self.value == self.expected

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "value": self.value,
            "expected": self.expected,
            "matches": self.matches,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class IntegrityReport:
    """Everything that was checked, and the verdict.

    ``status`` is ``VERIFIED`` only if every check that could run passed. Checks that could not
    run are listed as skipped, so a report never claims more than was looked at.
    """

    status: VerificationStatus
    level: VerifyLevel
    checks: tuple[Check, ...] = ()
    segments_checked: int = 0
    checksum: ChecksumResult | None = None
    #: What ffprobe found in the finished file (``strong`` verification, when it is installed).
    media: FileInfo | None = None
    elapsed_seconds: float = 0.0
    #: Where an output that failed was moved to, if it was kept.
    invalid_path: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def verified(self) -> bool:
        return self.status is VerificationStatus.VERIFIED

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.status is CheckStatus.FAILED)

    def summary(self) -> str:
        """One line saying what was found."""
        if self.verified:
            done = sum(1 for c in self.checks if c.status is CheckStatus.PASSED)
            return f"Verified: {done} check(s) passed."
        if self.failures:
            first = self.failures[0]
            more = f" (and {len(self.failures) - 1} more)" if len(self.failures) > 1 else ""
            return f"Verification failed: {first.name}: {first.detail}{more}"
        return f"Verification {self.status.value}."

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "level": self.level.value,
            "checks": [c.to_dict() for c in self.checks],
            "segments_checked": self.segments_checked,
            "checksum": self.checksum.to_dict() if self.checksum else None,
            "media": self.media.to_dict() if self.media else None,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "invalid_path": self.invalid_path,
            "notes": list(self.notes),
        }
