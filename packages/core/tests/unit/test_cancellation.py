import threading

import pytest

from rayohx import CancellationToken
from rayohx.errors import CancellationError


def test_token_starts_clear_and_cancels_once() -> None:
    token = CancellationToken()
    assert not token.is_cancelled
    token.raise_if_cancelled()
    token.cancel()
    token.cancel()
    assert token.is_cancelled
    with pytest.raises(CancellationError, match="cancelled"):
        token.raise_if_cancelled()


def test_wait_returns_at_once_when_cancelled() -> None:
    token = CancellationToken()
    assert token.wait(0.01) is False
    token.cancel()
    assert token.wait(60) is True


def test_wait_wakes_when_another_thread_cancels() -> None:
    token = CancellationToken()
    timer = threading.Timer(0.05, token.cancel)
    timer.start()
    try:
        assert token.wait(5) is True
    finally:
        timer.join()


def test_pause_and_resume_toggle_the_paused_flag() -> None:
    token = CancellationToken()
    assert not token.is_paused
    token.pause()
    assert token.is_paused
    assert token.wait_resumed(0.01) is False
    token.resume()
    assert not token.is_paused
    assert token.wait_resumed(0.01) is True


def test_cancelling_wins_over_pausing() -> None:
    token = CancellationToken()
    token.pause()
    token.cancel()
    assert token.is_cancelled
    assert not token.is_paused
    assert token.wait_resumed(60) is True
    token.pause()
    assert not token.is_paused


def test_wait_resumed_wakes_when_another_thread_resumes() -> None:
    token = CancellationToken()
    token.pause()
    timer = threading.Timer(0.05, token.resume)
    timer.start()
    try:
        assert token.wait_resumed(5) is True
    finally:
        timer.join()
