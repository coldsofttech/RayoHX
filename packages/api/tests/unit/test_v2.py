"""``/api/v2``: the persistent queue and the event log."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from rayohx.enums import DownloadState
from rayohx.models import DownloadProgress

from rayohx_api.config import get_settings
from rayohx_api.main import create_app
from rayohx_api.routers.v1 import reset_state

URL = "https://cdn.example.com/{}.m3u8"


class BlockingDownloader:
    """Runs until cancelled, like a long download."""

    def __init__(self, url: str, *, cancel: object, **_: object) -> None:
        from rayohx.events import EventBus

        self.events = EventBus()
        self.exception = None
        self._token = cancel

    def run(self) -> object:
        class Result:
            state = DownloadState.CANCELLED
            progress = DownloadProgress()
            error = None
            output = None

        from rayohx.enums import EventType
        from rayohx.events import DownloadEvent

        self.events.emit(
            DownloadEvent(
                type=EventType.DOWNLOAD_STARTED,
                download_id="x",
                state=DownloadState.DOWNLOADING,
                progress=DownloadProgress(state=DownloadState.DOWNLOADING),
            )
        )
        self._token.wait(10)  # type: ignore[attr-defined]
        return Result()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("RAYOHX_API_DOWNLOAD_DIR", str(tmp_path / "dl"))
    monkeypatch.setenv("RAYOHX_API_DEFAULTS_FILE", str(tmp_path / "defaults.json"))
    monkeypatch.setenv("RAYOHX_API_MAX_ACTIVE_DOWNLOADS", "1")
    monkeypatch.setattr("rayohx_api.service.Downloader", BlockingDownloader)
    get_settings.cache_clear()
    reset_state()
    return TestClient(create_app())


def add(client: TestClient, name: str, **body: object) -> dict:
    response = client.post("/api/v2/queue", json={"url": URL.format(name), **body})
    assert response.status_code == 202, response.text
    return response.json()["items"][0]


def names(client: TestClient, state: str = "queued") -> list[str]:
    items = client.get(f"/api/v2/queue?state={state}").json()["items"]
    return [i["url"].rsplit("/", 1)[1].removesuffix(".m3u8") for i in items]


def wait_state(client: TestClient, job_id: str, state: str) -> None:
    for _ in range(100):
        if client.get(f"/api/v2/queue/{job_id}").json()["state"] == state:
            return
        time.sleep(0.05)
    raise AssertionError(f"{job_id} never became {state}")


def test_jobs_wait_in_priority_order_and_the_first_one_runs(client: TestClient) -> None:
    first = add(client, "first")
    wait_state(client, first["id"], "downloading")
    low = add(client, "low", priority="low")
    high = add(client, "high", priority="high")
    assert names(client) == ["high", "low"]
    listing = client.get("/api/v2/queue?state=queued").json()
    assert [i["priority"] for i in listing["items"]] == ["high", "low"]
    assert listing["stats"]["active"] == 1
    assert listing["stats"]["max_active"] == 1
    assert listing["stats"]["runner"] == "this process"
    assert low["max_attempts"] == 3
    assert high["rank"] > 0


def test_actions_apply_to_many_jobs_and_report_each(client: TestClient) -> None:
    running = add(client, "run")
    wait_state(client, running["id"], "downloading")
    waiting = add(client, "wait")
    result = client.post(
        "/api/v2/queue/actions",
        json={"action": "pause", "ids": [running["id"], waiting["id"], "ghost"]},
    ).json()
    assert sorted(result["done"]) == sorted([running["id"], waiting["id"]])
    assert result["failed"] == {"ghost": "No such job."}
    wait_state(client, running["id"], "paused")
    assert client.get(f"/api/v2/queue/{waiting['id']}").json()["state"] == "paused"
    resumed = client.post(
        "/api/v2/queue/actions", json={"action": "resume", "ids": [waiting["id"]]}
    ).json()
    assert resumed["done"] == [waiting["id"]]
    cancelled = client.post(
        "/api/v2/queue/actions", json={"action": "cancel", "ids": [running["id"], waiting["id"]]}
    ).json()
    assert len(cancelled["done"]) == 2
    wait_state(client, waiting["id"], "cancelled")
    removed = client.post(
        "/api/v2/queue/actions", json={"action": "remove", "ids": [running["id"]]}
    ).json()
    assert removed["done"] == [running["id"]]


def test_priority_and_ordering_actions(client: TestClient) -> None:
    blocker = add(client, "blocker")
    wait_state(client, blocker["id"], "downloading")
    a, b, c = (add(client, n) for n in "abc")
    assert names(client) == ["a", "b", "c"]
    client.post("/api/v2/queue/actions", json={"action": "top", "ids": [c["id"]]})
    assert names(client) == ["c", "a", "b"]
    client.post("/api/v2/queue/actions", json={"action": "bottom", "ids": [c["id"]]})
    assert names(client) == ["a", "b", "c"]
    moved = client.post(f"/api/v2/queue/{c['id']}/move", json={"before": a["id"]})
    assert moved.status_code == 200
    assert names(client) == ["c", "a", "b"]
    client.post(
        "/api/v2/queue/actions", json={"action": "priority", "ids": [b["id"]], "priority": "high"}
    )
    assert names(client) == ["b", "c", "a"]
    missing = client.post("/api/v2/queue/actions", json={"action": "priority", "ids": [b["id"]]})
    assert missing.status_code == 422
    assert client.post("/api/v2/queue/ghost/move", json={"before": a["id"]}).status_code == 404
    assert client.post(f"/api/v2/queue/{a['id']}/move", json={"before": "ghost"}).status_code == 404


def test_one_job_has_a_run_history(client: TestClient) -> None:
    job = add(client, "one")
    wait_state(client, job["id"], "downloading")
    client.post("/api/v2/queue/actions", json={"action": "pause", "ids": [job["id"]]})
    wait_state(client, job["id"], "paused")
    detail = client.get(f"/api/v2/queue/{job['id']}").json()
    assert [a["outcome"] for a in detail["attempt_history"]] == ["pause"]
    assert detail["attempts"] == 1
    assert client.get("/api/v2/queue/ghost").status_code == 404


def test_the_queue_survives_a_restart(client: TestClient) -> None:
    running = add(client, "run")
    wait_state(client, running["id"], "downloading")
    waiting = add(client, "wait", priority="high")
    reset_state()  # the API process ends: running jobs go back to the queue
    again = TestClient(create_app())
    items = again.get("/api/v2/queue").json()["items"]
    assert {i["id"] for i in items} == {running["id"], waiting["id"]}
    assert {i["state"] for i in items} <= {"queued", "preparing", "downloading"}


def test_bad_input_is_422(client: TestClient) -> None:
    assert client.post("/api/v2/queue", json={"url": "ftp://x"}).status_code == 422
    assert (
        client.post(
            "/api/v2/queue", json={"url": URL.format("a"), "priority": "urgent"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v2/queue", json={"url": URL.format("a"), "retry": {"max_attempts": 0}}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/v2/queue/actions", json={"action": "pause", "ids": []}).status_code == 422
    )
    assert (
        client.post("/api/v2/queue/actions", json={"action": "explode", "ids": ["a"]}).status_code
        == 422
    )
    assert client.put("/api/v2/queue/settings", json={"max_active": 0}).status_code == 422


def test_how_many_jobs_run_at_once_can_change(client: TestClient) -> None:
    stats = client.put("/api/v2/queue/settings", json={"max_active": 3}).json()
    assert stats["max_active"] == 3
    assert client.get("/api/v2/queue/stats").json()["max_active"] == 3


def test_the_event_log_can_be_followed_by_id(client: TestClient) -> None:
    job = add(client, "ev")
    wait_state(client, job["id"], "downloading")
    everything = client.get("/api/v2/events").json()
    types = [e["type"] for e in everything["items"]]
    assert "queue.job_added" in types
    assert everything["last_id"] == everything["items"][-1]["id"]
    nothing_new = client.get(f"/api/v2/events?after_id={everything['last_id']}").json()
    assert nothing_new["items"] == []
    assert nothing_new["last_id"] == everything["last_id"]
    only_job = client.get(f"/api/v2/events?job_id={job['id']}&category=queue").json()
    assert only_job["items"]
    assert {e["job_id"] for e in only_job["items"]} == {job["id"]}
    assert client.get("/api/v2/events?category=nonsense").status_code == 422


def test_events_stream_starts_after_the_cursor(client: TestClient) -> None:
    job = add(client, "stream")
    wait_state(client, job["id"], "downloading")
    with client.stream("GET", "/api/v2/events/stream?after_id=0") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = []
        for line in response.iter_lines():
            lines.append(line)
            if sum(1 for x in lines if x.startswith("id: ")) >= 2:
                break
    assert any(x == "event: platform" for x in lines)
    assert any("queue.job_added" in x for x in lines)


def test_secrets_never_appear_in_responses(client: TestClient) -> None:
    job = add(
        client,
        "sec",
        network={"headers": {"Authorization": "Bearer HUSH"}, "cookies": {"sid": "HUSH"}},
    )
    wait_state(client, job["id"], "downloading")
    for path in (
        "/api/v2/queue",
        f"/api/v2/queue/{job['id']}",
        "/api/v2/events",
        "/api/v1/downloads",
    ):
        assert "HUSH" not in client.get(path).text, path


def test_huge_cursors_are_refused_not_crashed(client: TestClient) -> None:
    assert client.get("/api/v2/events?after_id=9223372036854775808").status_code == 422
    assert client.get("/api/v2/events?after_id=9223372036854775807").status_code == 200
    with client.stream(
        "GET", "/api/v2/events/stream", headers={"Last-Event-ID": "99999999999999999999999"}
    ) as response:
        assert response.status_code == 200
