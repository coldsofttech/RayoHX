from typing import Any

import pytest
from fastapi.testclient import TestClient
from rayohx_testing.fixtures import fixture_text

URL = "https://cdn.example.com/m.m3u8"
MASTER = fixture_text("hls/master_two_variants.m3u8")


def test_inspect_lists_variants(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from rayohx.playlist import inspect_text

    monkeypatch.setattr(
        "rayohx.playlist.inspection.inspect",
        lambda url, network=None: inspect_text(MASTER, url),
    )
    body = client.post("/api/v1/inspect", json={"url": URL}).json()
    assert [v["resolution"] for v in body["playlist"]["variants"]] == ["640x360", "1280x720"]


def test_inspect_forwards_url_and_headers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rayohx.playlist import inspect_text

    seen: dict[str, Any] = {}

    def fake(url: str, network: Any = None) -> Any:
        seen.update(url=url, headers=dict(network.headers))
        return inspect_text(MASTER, url)

    monkeypatch.setattr("rayohx.playlist.inspection.inspect", fake)
    response = client.post(
        "/api/v1/inspect", json={"url": URL, "network": {"headers": {"Referer": "https://a.test"}}}
    )
    assert response.status_code == 200
    assert seen == {"url": URL, "headers": {"Referer": "https://a.test"}}


def test_inspect_bad_url_is_problem_422(client: TestClient) -> None:
    response = client.post("/api/v1/inspect", json={"url": "ftp://nope"})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


def test_inspect_engine_error_is_422(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from rayohx.errors import RayoHXError

    def boom(url: str, network: Any = None) -> None:
        raise RayoHXError("not a playlist")

    monkeypatch.setattr("rayohx.playlist.inspection.inspect", boom)
    response = client.post("/api/v1/inspect", json={"url": URL})
    assert response.status_code == 422
    assert "not a playlist" in response.json()["detail"]


@pytest.mark.parametrize("body", [{}, {"url": ""}, {"url": URL, "quality": "fast"}])
def test_inspect_validates_body(client: TestClient, body: dict[str, Any]) -> None:
    response = client.post("/api/v1/inspect", json=body)
    assert response.status_code == 422
    assert response.json()["errors"]
