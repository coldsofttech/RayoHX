"""Cooperative control of running work: ask it to stop, or to pause and continue."""


class CancellationToken:
    """A flag that one thread sets and many workers check. Safe to share across threads.

    The same token can also pause work: while it is paused, a download starts no new segments
    (those already running finish), and ``resume`` lets it go on. Cancelling wins over pausing.
    """

    def __init__(self) -> None:
        import threading

        self._event = threading.Event()
        self._running = threading.Event()
        self._running.set()

    def cancel(self) -> None:
        """Ask everything holding this token to stop. Calling it again does nothing."""
        self._event.set()
        self._running.set()  # wake anything waiting to be resumed

    def pause(self) -> None:
        """Ask work holding this token to wait. Does nothing once cancelled."""
        if not self._event.is_set():
            self._running.clear()

    def resume(self) -> None:
        """Let paused work go on."""
        self._running.set()

    @property
    def is_paused(self) -> bool:
        """Whether work should wait, and has not been cancelled."""
        return not self._running.is_set()

    def wait_resumed(self, timeout: float) -> bool:
        """Sleep up to ``timeout`` seconds, waking at once if resumed or cancelled."""
        return self._running.wait(timeout)

    @property
    def is_cancelled(self) -> bool:
        """Whether cancellation has been requested."""
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        """Raise ``CancellationError`` if cancellation has been requested."""
        if self._event.is_set():
            from rayohx.errors import CancellationError

            raise CancellationError("The download was cancelled.")

    def wait(self, timeout: float) -> bool:
        """Sleep up to ``timeout`` seconds, waking at once if cancelled. True means cancelled."""
        return self._event.wait(timeout)
