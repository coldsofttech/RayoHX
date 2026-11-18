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


# --- profiles ----------------------------------------------------------------------------------


def test_profiles_and_capabilities_are_listed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rayohx.capabilities import Capabilities

    monkeypatch.setattr("rayohx_api.routers.v2.detect", lambda: Capabilities())
    monkeypatch.setattr("rayohx.platform.profiles.rules.detect", lambda _p=None: Capabilities())
    items = client.get("/api/v2/profiles").json()["items"]
    assert [p["id"] for p in items] == ["best-quality", "1080p", "mobile", "archive", "custom"]
    archive = next(p for p in items if p["id"] == "archive")
    assert archive["builtin"] is True
    assert "FFmpeg" in archive["problems"][0]
    assert [p["problems"] for p in items if p["id"] == "mobile"] == [[]]
    assert (
        client.get("/api/v2/profiles/mobile").json()["options"]["selection"]["max_resolution"]
        == "480p"
    )
    assert client.get("/api/v2/profiles/ghost").status_code == 404
    caps = client.get("/api/v2/capabilities").json()
    assert caps["ffmpeg"] is None
    assert caps["formats"]["mkv"] is False
    assert caps["formats"]["mp4"] is True


def queued_options(client: TestClient, job_id: str) -> dict:
    from rayohx_api.service import rayo

    record = rayo().queue.get(job_id)
    assert record is not None
    return dict(record.spec.options)


def test_a_request_can_name_a_profile(client: TestClient) -> None:
    job = add(client, "p", profile="mobile")
    assert job["profile"] == "mobile"
    options = queued_options(client, job["id"])
    assert options["selection"]["max_resolution"] == "480p"
    assert options["output"]["format"] == "mp4"
    assert client.get(f"/api/v2/queue/{job['id']}").json()["profile"] == "mobile"


def test_only_what_the_request_sets_overrides_the_profile(client: TestClient) -> None:
    job = add(
        client, "o", profile="mobile",
        selection={"max_resolution": "720p"}, output={"directory": "shows"},
    )  # fmt: skip
    options = queued_options(client, job["id"])
    assert options["selection"]["max_resolution"] == "720p"  # set in the request
    assert options["selection"]["max_bitrate"] == 1_500_000  # the profile's
    assert options["output"]["format"] == "mp4"  # not set in the request: the profile's
    assert options["output"]["directory"].endswith("shows")


def test_the_default_profile_applies_and_secrets_stay_out(client: TestClient) -> None:
    from rayohx_api.service import rayo

    rayo().profiles.set_default("1080p")
    job = add(client, "d", network={"headers": {"Authorization": "Bearer HUSH"}, "retries": 7})
    assert job["profile"] == "1080p"
    options = queued_options(client, job["id"])
    assert options["selection"]["max_resolution"] == "1080p"
    assert options["network"]["retries"] == 7
    assert options["network"]["headers"] == {}
    assert "HUSH" not in client.get("/api/v2/queue").text


def test_no_profile_keeps_the_saved_defaults_behavior(client: TestClient) -> None:
    client.put("/api/v1/settings/defaults", json={"selection": {"quality": "720p"}})
    job = add(client, "legacy")
    assert job["profile"] is None
    assert queued_options(client, job["id"])["selection"]["quality"] == "720p"


def test_profile_errors_are_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from rayohx.capabilities import Capabilities

    response = client.post("/api/v2/queue", json={"url": URL.format("a"), "profile": "ghost"})
    assert response.status_code == 422
    assert "no profile" in response.json()["detail"]
    monkeypatch.setattr("rayohx.platform.profiles.rules.detect", lambda _p=None: Capabilities())
    needs = client.post("/api/v2/queue", json={"url": URL.format("a"), "profile": "archive"})
    assert needs.status_code == 422
    assert "FFmpeg" in needs.json()["detail"]
    assert client.get("/api/v2/queue").json()["items"] == []


def test_the_new_output_formats_are_accepted(client: TestClient) -> None:
    for fmt in ("original", "mkv", "audio"):
        response = client.post(
            "/api/v1/downloads", json={"url": URL.format(fmt), "output": {"format": fmt}}
        )
        assert response.status_code in {202, 422}, fmt  # 422 only if FFmpeg is missing
    assert (
        client.post(
            "/api/v1/downloads", json={"url": URL.format("x"), "output": {"format": "avi"}}
        ).status_code
        == 422
    )
