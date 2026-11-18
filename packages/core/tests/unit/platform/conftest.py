import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from rayohx.platform import Rayo
from rayohx.platform.jobs import JobState
from rayohx.platform.secrets import MemorySecretStore
from tests.unit.platform import fakes


@pytest.fixture
def make_rayo(tmp_path: Path) -> Iterator[Callable[..., Rayo]]:
    """Build platforms over one folder; all are closed at the end."""
    created: list[Rayo] = []
    fakes.reset()

    def build(**kwargs: object) -> Rayo:
        options: dict[str, object] = {
            "home": tmp_path / "home",
            "download_dir": tmp_path / "downloads",
            "secrets": MemorySecretStore(),
            "downloader_factory": fakes.FakeDownloader,
        }
        options.update(kwargs)
        rayo = Rayo(**options)  # type: ignore[arg-type]
        created.append(rayo)
        return rayo

    yield build
    for rayo in reversed(created):
        rayo.close()
    fakes.reset()


@pytest.fixture
def rayo(make_rayo: Callable[..., Rayo]) -> Rayo:
    return make_rayo()


def wait_for(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting for the condition")
        time.sleep(0.01)


def state_of(rayo: Rayo, job_id: str) -> JobState:
    job = rayo.queue.get(job_id)
    assert job is not None
    return job.state


def wait_state(rayo: Rayo, job_id: str, state: JobState, timeout: float = 5.0) -> None:
    wait_for(lambda: state_of(rayo, job_id) is state, timeout)
