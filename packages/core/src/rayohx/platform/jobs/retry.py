"""When a failed job is tried again, and how long to wait."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rayohx.enums import ErrorCategory
from rayohx.errors import RayoHXError

DEFAULT_RETRY_CATEGORIES = frozenset(
    {ErrorCategory.NETWORK, ErrorCategory.HTTP, ErrorCategory.SEGMENT}
)


@dataclass(frozen=True, slots=True, kw_only=True)
class RetryPolicy:
    """Retry a failed job a few times, with growing waits, for problems that may pass.

    This is separate from the engine's own retries of single requests. It decides whether the
    *whole job* is run again, and it keeps what was already downloaded.
    """

    #: Runs allowed in total, the first one included. ``1`` means never retry.
    max_attempts: int = 3
    initial_delay: float = 10.0
    factor: float = 2.0
    max_delay: float = 600.0
    categories: frozenset[ErrorCategory] = DEFAULT_RETRY_CATEGORIES

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.initial_delay < 0 or self.max_delay < 0 or self.factor < 1:
            raise ValueError("delays must not be negative and the factor must be at least 1")

    def delay_for(self, attempts_made: int) -> float:
        """Seconds to wait after the ``attempts_made``-th failed run."""
        delay = self.initial_delay * (self.factor ** max(0, attempts_made - 1))
        return float(min(delay, self.max_delay))

    def should_retry(self, error: BaseException | None, attempts_made: int) -> bool:
        """Whether to run the job again after it failed with ``error``."""
        if attempts_made >= self.max_attempts or not isinstance(error, RayoHXError):
            return False
        if error.category not in self.categories:
            return False
        retryable = getattr(error, "retryable", None)
        return True if retryable is None else bool(retryable)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "initial_delay": self.initial_delay,
            "factor": self.factor,
            "max_delay": self.max_delay,
            "categories": sorted(c.value for c in self.categories),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetryPolicy:
        known = {
            "max_attempts": int,
            "initial_delay": float,
            "factor": float,
            "max_delay": float,
        }
        values: dict[str, Any] = {k: kind(data[k]) for k, kind in known.items() if k in data}
        if "categories" in data:
            values["categories"] = frozenset(ErrorCategory(c) for c in data["categories"])
        return cls(**values)


#: Never retry.
NO_RETRY = RetryPolicy(max_attempts=1)
