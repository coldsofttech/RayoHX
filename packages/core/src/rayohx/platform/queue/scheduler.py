"""Deciding which queued jobs run next.

``pick_next`` is a pure function: the same input always gives the same answer, on every platform.
That makes the order easy to test and easy to explain:

1. Higher priority first (``HIGH`` before ``NORMAL`` before ``LOW``).
2. Within a priority, the order the user arranged (``rank``, smallest first).
3. Then the job added first, then the smaller id, so ties are never random.

Resource checks (such as free disk space) may skip a job for now, but they never reorder the rest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


@dataclass(frozen=True, slots=True)
class Candidate:
    """A queued job as the scheduler sees it."""

    id: str
    priority: int
    rank: float
    created_at: float
    not_before: float | None = None


def order_key(candidate: Candidate) -> tuple[int, float, float, str]:
    return (-candidate.priority, candidate.rank, candidate.created_at, candidate.id)


def pick_next(
    candidates: Iterable[Candidate],
    *,
    free_slots: int,
    now: float,
    admit: Callable[[Candidate], bool] | None = None,
) -> list[str]:
    """The ids to start now, in start order, at most ``free_slots`` of them.

    A job whose ``not_before`` is still in the future (a retry waiting out its delay) is not
    ready. ``admit`` may refuse a job for now; a refused job does not use a slot, so the next
    one in line gets it.
    """
    if free_slots <= 0:
        return []
    ready = [c for c in candidates if c.not_before is None or c.not_before <= now]
    chosen: list[str] = []
    for candidate in sorted(ready, key=order_key):
        if admit is not None and not admit(candidate):
            continue
        chosen.append(candidate.id)
        if len(chosen) == free_slots:
            break
    return chosen
