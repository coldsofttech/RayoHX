from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rayohx_api.config import get_settings
from rayohx_api.main import create_app
from rayohx_api.routers.v1 import reset_state

MASTER = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360
low.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720
high.m3u8
"""


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("RAYOHX_API_DOWNLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    reset_state()
    return TestClient(create_app())


def test_inspect_lists_variants(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from rayohx.playlist import inspect_text

    monkeypatch.setattr(
        "rayohx_api.routers.v1.inspect",
        lambda url, network=None: inspect_text(MASTER, url),
    )
    body = client.post("/api/v1/inspect", json={"url": "https://cdn.example.com/m.m3u8"}).json()
    assert [v["resolution"] for v in body["playlist"]["variants"]] == ["640x360", "1280x720"]


def test_inspect_bad_url_is_422(client: TestClient) -> None:
    response = client.post("/api/v1/inspect", json={"url": "ftp://nope"})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


def test_filename_cannot_escape_folder(client: TestClient) -> None:
    response = client.post(
        "/api/v1/downloads", json={"url": "https://cdn.example.com/m.m3u8", "filename": "../x.mp4"}
    )
    assert response.status_code == 422


def test_unknown_download_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/downloads/nope").status_code == 404
    assert client.get("/api/v1/downloads").json() == {"items": []}


def test_settings_roundtrip(client: TestClient) -> None:
    assert client.get("/api/v1/settings").json()["concurrency"] == 4
    updated = client.patch("/api/v1/settings", json={"concurrency": 8, "quality": "720p"}).json()
    assert (updated["concurrency"], updated["quality"]) == (8, "720p")
    assert client.patch("/api/v1/settings", json={"concurrency": 999}).status_code == 422


def test_clean_dry_run_then_remove(client: TestClient, tmp_path: Path) -> None:
    leftover = tmp_path / ".rayohx-abc"
    leftover.mkdir()
    (leftover / "part").write_bytes(b"x" * 10)
    dry = client.post("/api/v1/clean", json={}).json()
    assert dry["freed_bytes"] == 10
    assert leftover.exists()
    done = client.post("/api/v1/clean", json={"dry_run": False}).json()
    assert done["folders"][0]["name"] == ".rayohx-abc"
    assert not leftover.exists()


class FakeDownloader:
    """Stands in for the engine: runs until cancelled."""

    def __init__(self, url, *, cancel, events=None, **_):
        import threading

        from rayohx.events import EventBus

        self.events = EventBus()
        self.cancel_token = cancel
        self.paused = False
        self.started = threading.Event()

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def run(self):
        from rayohx.enums import DownloadState
        from rayohx.models import DownloadProgress

        class Result:
            state = DownloadState.CANCELLED
            progress = DownloadProgress()
            error = None
            output = None

        self.started.set()
        self.cancel_token.wait(5)
        return Result()


def test_download_lifecycle(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    monkeypatch.setattr("rayohx_api.jobs.Downloader", FakeDownloader)
    created = client.post(
        "/api/v1/downloads",
        json={"url": "https://cdn.example.com/m.m3u8?token=secret", "filename": "a.mp4"},
    )
    assert created.status_code == 202
    job = created.json()["items"][0]
    assert "secret" not in job["url"]
    assert client.post(f"/api/v1/downloads/{job['id']}/pause").status_code == 200
    assert client.post(f"/api/v1/downloads/{job['id']}/resume").status_code == 200
    assert client.delete(f"/api/v1/downloads/{job['id']}").status_code == 409
    client.post(f"/api/v1/downloads/{job['id']}/cancel")
    for _ in range(50):
        if client.get(f"/api/v1/downloads/{job['id']}").json()["state"] == "cancelled":
            break
        time.sleep(0.1)
    assert client.get(f"/api/v1/downloads/{job['id']}").json()["state"] == "cancelled"
    events = client.get(f"/api/v1/downloads/{job['id']}/events")
    assert "event: job" in events.text
    assert client.delete(f"/api/v1/downloads/{job['id']}").status_code == 204
    assert client.get("/api/v1/downloads").json() == {"items": []}


def post(client: TestClient, **body: object):
    return client.post("/api/v1/downloads", json={"url": "https://cdn.example.com/m.m3u8", **body})


def test_local_files_are_refused_by_default(client: TestClient) -> None:
    for network in ({"cookie_file": "/etc/passwd"}, {"client_cert": "/x.pem"}, {"ca_bundle": "/c"}):
        response = post(client, network=network)
        assert response.status_code == 422, network
        assert "ALLOW_LOCAL_PATHS" in response.json()["detail"]
    assert post(client, engine={"allow_file_keys": True}).status_code == 422
    assert post(client, output={"ffmpeg": "/bin/ffmpeg"}).status_code == 422


def test_folders_cannot_leave_download_dir(client: TestClient) -> None:
    for bad in ("../x", "/srv/x", "a/../../x"):
        assert post(client, output={"directory": bad}).status_code == 422
        assert post(client, storage={"workspace": bad}).status_code == 422


def test_conflicting_selection_is_422(client: TestClient) -> None:
    response = post(client, selection={"variant": 1, "codec": "hevc"})
    assert response.status_code == 422
    assert "variant" in response.json()["detail"]


def test_playlist_text_needs_base_url(client: TestClient) -> None:
    response = client.post("/api/v1/inspect", json={"playlist_text": MASTER})
    assert response.status_code == 422
    ok = client.post(
        "/api/v1/inspect",
        json={"playlist_text": MASTER, "base_url": "https://cdn.example.com/a/m.m3u8"},
    )
    assert len(ok.json()["playlist"]["variants"]) == 2


def test_batch_and_options(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rayohx_api.jobs.Downloader", FakeDownloader)
    response = client.post(
        "/api/v1/downloads",
        json={
            "urls": ["https://a.example.com/x.m3u8", "https://b.example.com/x.m3u8"],
            "network": {
                "proxy": {"url": "socks5h://127.0.0.1:1080", "username": "u", "password": "s3cret"},
                "cookies": {"a": "b"},
                "retries": 5,
            },
            "selection": {"codec": "hevc", "max_frame_rate": 30, "audio_names": ["English"]},
            "storage": {"strategy": "buffered", "reserve_bytes": 0},
            "output": {"format": "mp4", "directory": "shows", "validate": False},
            "engine": {"concurrency": 8, "resume": False},
        },
    )
    assert response.status_code == 202
    jobs = response.json()["items"]
    assert len(jobs) == 2
    assert "s3cret" not in str(jobs)
    for job in jobs:
        client.post(f"/api/v1/downloads/{job['id']}/cancel")


def test_filename_with_batch_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/downloads",
        json={"urls": ["https://a/x.m3u8", "https://b/x.m3u8"], "filename": "a.mp4"},
    )
    assert response.status_code == 422


def test_local_paths_allowed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from rayohx_api.build import read_cookie_file

    cookies = tmp_path / "c.txt"
    cookies.write_text("# c\n.example.com\tTRUE\t/\tFALSE\t0\tsid\tabc\n")
    assert read_cookie_file(cookies) == {"sid": "abc"}
    bad = tmp_path / "bad.txt"
    bad.write_text("nope\n")
    from rayohx.errors import ConfigurationError

    with pytest.raises(ConfigurationError):
        read_cookie_file(bad)
    monkeypatch.setenv("RAYOHX_API_ALLOW_LOCAL_PATHS", "true")
    monkeypatch.setenv("RAYOHX_API_DOWNLOAD_DIR", str(tmp_path))
    get_settings.cache_clear()
    reset_state()
    monkeypatch.setattr("rayohx_api.jobs.Downloader", FakeDownloader)
    client = TestClient(create_app())
    response = client.post(
        "/api/v1/downloads",
        json={"url": "https://cdn.example.com/m.m3u8", "network": {"cookie_file": str(cookies)}},
    )
    assert response.status_code == 202
    client.post(f"/api/v1/downloads/{response.json()['items'][0]['id']}/cancel")
