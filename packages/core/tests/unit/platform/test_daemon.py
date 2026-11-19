"""The daemon: it runs the queue, answers health checks and stops cleanly."""

import io
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from rayohx.platform import Rayo
from rayohx.platform.daemon import Daemon, JsonFormatter, configure_logging
from rayohx.platform.errors import RunnerLockedError
from rayohx.platform.jobs import JobState
from tests.unit.platform.conftest import wait_state


def get(daemon: Daemon, path: str) -> tuple[int, str]:
    url = f"http://127.0.0.1:{daemon.health_port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


@pytest.fixture
def daemon(make_rayo: Callable[..., Rayo]) -> Iterator[Daemon]:
    service = Daemon(make_rayo(), port=0, metrics=True)
    service.start()
    yield service
    service.stop()


def test_health_ready_and_metrics(daemon: Daemon) -> None:
    status, body = get(daemon, "/health")
    data = json.loads(body)
    assert status == 200
    assert data["status"] == "ok"
    assert data["runner"] == "this process"
    assert data["storage"] == "ok"
    assert get(daemon, "/ready") == (200, '{"ready": true}')
    status, text = get(daemon, "/metrics")
    assert status == 200
    assert "rayohx_queue_queued" in text
    assert get(daemon, "/nothing")[0] == 404
    assert get(daemon, "/health?x=1")[0] == 200


def test_metrics_are_off_unless_asked(make_rayo: Callable[..., Rayo]) -> None:
    service = Daemon(make_rayo(), port=0)
    service.start()
    try:
        assert get(service, "/metrics")[0] == 404
    finally:
        service.stop()


def test_it_runs_queued_jobs_and_stops_cleanly(make_rayo: Callable[..., Rayo]) -> None:
    rayo = make_rayo()
    job = rayo.queue.add("https://media.test/a/master.m3u8")
    service = Daemon(rayo, port=None)
    service.start()
    wait_state(rayo, job.id, JobState.COMPLETED)
    assert service.health_port is None
    service.stop()
    assert not rayo.queue.running


def test_a_second_daemon_is_refused(make_rayo: Callable[..., Rayo], tmp_path: Any) -> None:
    first = make_rayo()
    service = Daemon(first, port=None)
    service.start()
    try:
        second = Daemon(make_rayo(home=tmp_path / "home"), port=None)
        with pytest.raises(RunnerLockedError):
            second.start()
    finally:
        service.stop()


def test_stop_can_be_requested_from_another_thread(make_rayo: Callable[..., Rayo]) -> None:
    import threading

    service = Daemon(make_rayo(), port=None)
    threading.Timer(0.2, service.request_stop).start()
    service.run()  # returns once stop is requested
    assert not service.rayo.queue.running


def test_log_lines_are_json_without_secrets(make_rayo: Callable[..., Rayo]) -> None:
    stream = io.StringIO()
    handler = configure_logging(stream)
    try:
        rayo = make_rayo()
        service = Daemon(rayo, port=None)
        service.start()
        job = rayo.queue.add("https://media.test/a/master.m3u8?token=SuperSecretToken123")
        wait_state(rayo, job.id, JobState.COMPLETED)
        service.stop()
    finally:
        logging.getLogger("rayohx").removeHandler(handler)
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert lines
    assert {"time", "level", "message"} <= set(lines[0])
    assert any(line["message"] == "daemon started" for line in lines)
    assert any(line.get("event") == "queue.job_added" for line in lines)
    assert "SuperSecretToken123" not in stream.getvalue()


def test_the_formatter_never_prints_a_traceback() -> None:
    try:
        raise ValueError("secret detail")
    except ValueError:
        import sys

        record = logging.LogRecord("x", logging.ERROR, "f", 1, "boom", (), sys.exc_info())
    entry = json.loads(JsonFormatter().format(record))
    assert entry["error"] == "ValueError"
    assert "secret detail" not in json.dumps(entry)
