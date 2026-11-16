"""The download state machine and the event that describes what happened."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

from rayohx.enums import DownloadState
from rayohx.errors import InvalidStateTransitionError

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from rayohx.enums import EventType
    from rayohx.models.download.progress import DownloadProgress

_S = DownloadState

#: States each state may move to. Terminal states move nowhere.
TRANSITIONS: Mapping[DownloadState, frozenset[DownloadState]] = MappingProxyType(
    {
        _S.QUEUED: frozenset({_S.INSPECTING, _S.CANCELLED, _S.FAILED}),
        _S.INSPECTING: frozenset({_S.PREPARING, _S.CANCELLED, _S.FAILED}),
        _S.PREPARING: frozenset({_S.DOWNLOADING, _S.CANCELLED, _S.FAILED}),
        _S.DOWNLOADING: frozenset({_S.FINALIZING, _S.PAUSED, _S.CANCELLED, _S.FAILED}),
        _S.PAUSED: frozenset({_S.DOWNLOADING, _S.CANCELLED, _S.FAILED}),
        _S.FINALIZING: frozenset({_S.COMPLETED, _S.CANCELLED, _S.FAILED}),
        _S.COMPLETED: frozenset(),
        _S.FAILED: frozenset(),
        _S.CANCELLED: frozenset(),
    }
)


class DownloadStateMachine:
    """Holds the state of one download and allows only valid moves. Safe across threads."""

    def __init__(self, state: DownloadState = DownloadState.QUEUED) -> None:
        import threading

        self._state = state
        self._lock = threading.Lock()

    @property
    def state(self) -> DownloadState:
        """The current state."""
        with self._lock:
            return self._state

    def can_move_to(self, new_state: DownloadState) -> bool:
        """Whether ``new_state`` is reachable from the current state."""
        return new_state in TRANSITIONS[self.state]

    def move_to(self, new_state: DownloadState) -> DownloadState:
        """Move to ``new_state`` and return the state it left.

        Raises:
            InvalidStateTransitionError: If the move is not allowed.
        """
        with self._lock:
            old = self._state
            if new_state not in TRANSITIONS[old]:
                raise InvalidStateTransitionError(
                    f"A download cannot go from {old.value} to {new_state.value}."
                )
            self._state = new_state
            return old


@dataclass(frozen=True, slots=True, kw_only=True)
class DownloadEvent:
    """Something that happened during a download."""

    type: EventType
    download_id: str
    state: DownloadState
    timestamp: float = field(default_factory=time.time)
    progress: DownloadProgress | None = None
    segment_index: int | None = None
    message: str | None = None
    data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))
