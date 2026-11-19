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


def test_v1_keeps_the_saved_defaults_and_v2_uses_profiles(client: TestClient) -> None:
    client.put("/api/v1/settings/defaults", json={"selection": {"quality": "720p"}})
    legacy = client.post("/api/v1/downloads", json={"url": URL.format("legacy")}).json()["items"][0]
    assert queued_options(client, legacy["id"])["selection"]["quality"] == "720p"
    assert queued_options(client, legacy["id"])["verify"]["level"] == "none"  # exactly as before
    modern = add(client, "modern")
    assert modern["profile"] is None
    assert queued_options(client, modern["id"])["selection"]["quality"] == "best"


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


# --- verification, metadata, media information -------------------------------------------------

MEDIA = """#EXTM3U
#EXT-X-TARGETDURATION:4
#EXT-X-PLAYLIST-TYPE:VOD
#EXTINF:4,
seg0.ts
#EXTINF:4,
seg1.ts
#EXT-X-ENDLIST
"""


def test_the_queue_checks_and_labels_by_default(client: TestClient) -> None:
    job = add(client, "plain")
    options = queued_options(client, job["id"])
    assert options["verify"]["level"] == "basic"
    assert options["metadata"]["policy"] == "preserve"
    assert job["verification"] == "not_requested"
    assert job["notes"] == []


def test_a_request_can_set_verification_metadata_and_naming(client: TestClient) -> None:
    job = add(
        client, "set", profile="mobile",
        verify={"level": "strong", "checksum": "ab" * 32},
        metadata={"policy": "minimal", "title": "My film"},
        name_template="{title} [{date}]",
    )  # fmt: skip
    options = queued_options(client, job["id"])
    assert options["verify"]["level"] == "strong"
    assert options["verify"]["expected_checksum"] == "ab" * 32
    assert options["metadata"]["policy"] == "minimal"
    assert options["metadata"]["title"] == "My film"
    assert options["output"]["name_template"] == "{title} [{date}]"


def test_bad_verification_requests_are_422(client: TestClient) -> None:
    for body in (
        {"verify": {"level": "paranoid"}},
        {"verify": {"checksum": "xyz"}},
        {"verify": {"checksum": "abcd"}},
        {"metadata": {"policy": "everything"}},
        {"name_template": "{nope}"},
        {"name_template": "a/b"},
    ):
        response = client.post("/api/v2/queue", json={"url": URL.format("a"), **body})
        assert response.status_code == 422, body
    assert client.get("/api/v2/queue").json()["items"] == []


def test_the_verification_report_is_available_once_a_job_has_one(client: TestClient) -> None:
    import json

    from rayohx_api.service import rayo

    job = add(client, "v")
    assert client.get(f"/api/v2/queue/{job['id']}/verification").status_code == 404
    assert client.get("/api/v2/queue/ghost/verification").status_code == 404
    report = {
        "status": "verified", "level": "strong", "segments_checked": 2,
        "checks": [{"name": "streams", "status": "passed", "detail": "1 video, 1 audio"}],
        "checksum": {"algorithm": "sha256", "value": "ab", "expected": None, "matches": None},
        "media": None, "elapsed_seconds": 0.1, "invalid_path": None, "notes": [],
    }  # fmt: skip
    result = {"integrity": report, "notes": ["Metadata was not written."]}
    rayo().jobs.update(
        job["id"], verification="verified", result_json=json.dumps(result), state="completed"
    )
    shown = client.get(f"/api/v2/queue/{job['id']}/verification").json()
    assert shown["status"] == "verified"
    assert shown["checks"][0]["name"] == "streams"
    detail = client.get(f"/api/v2/queue/{job['id']}").json()
    assert detail["verification"] == "verified"
    assert detail["notes"] == ["Metadata was not written."]


def test_media_info_describes_a_stream_and_checks_a_format(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rayohx.capabilities import Capabilities

    monkeypatch.setattr("rayohx.media.info.detect", lambda _p=None: Capabilities())
    body = {
        "playlist_text": MEDIA,
        "base_url": "https://cdn.example.com/a/index.m3u8?token=SECRET",
        "probe": False,
        "format": "mkv",
    }
    response = client.post("/api/v2/media-info", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["media"]["segment_count"] == 2
    assert data["media"]["duration"] == 8.0
    assert data["media"]["container"] == "MPEG-TS"
    assert data["media"]["size"]["kind"] == "unavailable"
    assert "SECRET" not in response.text
    assert data["compatibility"][0]["level"] == "error"
    assert "needs FFmpeg" in data["compatibility"][0]["message"]
    fine = client.post("/api/v2/media-info", json={**body, "format": "ts"}).json()
    assert fine["compatibility"] == []


def test_media_info_asks_for_a_source(client: TestClient) -> None:
    assert client.post("/api/v2/media-info", json={}).status_code == 422
    assert client.post("/api/v2/media-info", json={"playlist_text": MEDIA}).status_code == 422
    assert client.post("/api/v2/media-info", json={"url": "ftp://x"}).status_code == 422


# --- storage, diagnostics and metrics ----------------------------------------------------


def test_storage_status_policy_and_cleanup(client: TestClient) -> None:
    status = client.get("/api/v2/storage").json()
    assert status["level"] == "ok"
    updated = client.put(
        "/api/v2/storage/policy", json={"warn_below": "10GB", "pause_below": "5GB"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["pause_below"] == 5 * 1024**3
    assert client.get("/api/v2/storage").json()["policy"]["warn_below"] == 10 * 1024**3
    bad = client.put("/api/v2/storage/policy", json={"warn_below": "1GB", "pause_below": "5GB"})
    assert bad.status_code == 422
    assert client.get("/api/v2/storage/workspaces").json() == []
    plan = client.post("/api/v2/storage/cleanup", json={}).json()
    assert plan["dry_run"] is True


def test_diagnostics_explain_codes_and_jobs(client: TestClient) -> None:
    code = client.get("/api/v2/diagnostics/explain/HTTP_403").json()
    assert code["code"] == "HTTP_403"
    assert code["next_steps"]
    assert client.get("/api/v2/diagnostics/jobs/ghost").status_code == 404
    job = add(client, "explained")
    found = client.get(f"/api/v2/diagnostics/jobs/{job['id']}").json()
    assert found["job"]["id"] == job["id"]
    assert found["explanation"] is None


def test_the_report_is_clean_and_listed(client: TestClient) -> None:
    secret = "SuperSecretToken123"
    job = client.post("/api/v2/queue", json={"url": f"{URL.format('s')}?token={secret}"}).json()[
        "items"
    ][0]
    report = client.post("/api/v2/diagnostics/report", json={"job_id": job["id"]})
    assert report.status_code == 200, report.text
    assert secret not in report.text
    assert report.json()["report"]["report"]["sanitized"] is True
    assert "/" not in report.json()["path"]
    assert len(client.get("/api/v2/diagnostics/reports").json()) == 1
    assert client.post("/api/v2/diagnostics/report", json={"job_id": "ghost"}).status_code == 422


def test_network_check_needs_an_address(client: TestClient) -> None:
    assert client.post("/api/v2/diagnostics/network", json={}).status_code == 422
    refused = client.post("/api/v2/diagnostics/network", json={"url": "ftp://x/y"})
    assert refused.status_code == 422


def test_metrics_as_json_and_prometheus(client: TestClient) -> None:
    add(client, "m")
    data = client.get("/api/v2/metrics").json()
    assert set(data) >= {"queue", "downloads", "storage", "verification"}
    text = client.get("/api/v2/metrics/prometheus")
    assert text.headers["content-type"].startswith("text/plain")
    assert "rayohx_queue_queued" in text.text


# --- version 1 saved defaults -------------------------------------------------------------


def test_saved_v1_defaults_become_a_profile_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import json

    defaults = tmp_path / "defaults.json"
    defaults.write_text(json.dumps({"selection": {"max_resolution": "480p"}}))
    monkeypatch.setenv("RAYOHX_API_DOWNLOAD_DIR", str(tmp_path / "dl"))
    monkeypatch.setenv("RAYOHX_API_DEFAULTS_FILE", str(defaults))
    get_settings.cache_clear()
    reset_state()
    client = TestClient(create_app())
    profiles = client.get("/api/v2/profiles").json()["items"]
    imported = [p for p in profiles if p["id"] == "default"]
    assert len(imported) == 1
    assert imported[0]["options"]["selection"]["max_resolution"] == "480p"
    assert defaults.exists()  # the old file is kept
    reset_state()
    TestClient(create_app()).get("/api/v2/profiles")
    again = TestClient(create_app()).get("/api/v2/profiles").json()["items"]
    assert len([p for p in again if p["id"].startswith("default")]) == 1
