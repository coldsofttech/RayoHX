from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from rayohx import __version__
from rayohx.config.download import MAX_CONCURRENCY


def test_read_defaults(client: TestClient, tmp_path: Path) -> None:
    assert client.get("/api/v1/settings").json() == {
        "download_dir": str(tmp_path),
        "max_active_downloads": 2,
        "allow_local_paths": False,
        "concurrency": 4,
        "quality": "best",
        "overwrite": False,
        "limits": {"min_concurrency": 1, "max_concurrency": MAX_CONCURRENCY},
        "version": __version__,
    }


def test_settings_roundtrip(client: TestClient) -> None:
    assert client.get("/api/v1/settings").json()["concurrency"] == 4
    updated = client.patch("/api/v1/settings", json={"concurrency": 8, "quality": "720p"}).json()
    assert (updated["concurrency"], updated["quality"]) == (8, "720p")
    assert client.get("/api/v1/settings").json() == updated


def test_patch_changes_only_given_fields(client: TestClient) -> None:
    client.patch("/api/v1/settings", json={"concurrency": 8})
    after = client.patch("/api/v1/settings", json={"overwrite": True}).json()
    assert (after["concurrency"], after["overwrite"], after["quality"]) == (8, True, "best")


def test_empty_and_null_patches_change_nothing(client: TestClient) -> None:
    before = client.get("/api/v1/settings").json()
    assert client.patch("/api/v1/settings", json={}).json() == before
    nulls = {"concurrency": None, "quality": None, "overwrite": None}
    assert client.patch("/api/v1/settings", json=nulls).json() == before


def test_changes_do_not_touch_server_settings(client: TestClient, tmp_path: Path) -> None:
    after = client.patch("/api/v1/settings", json={"concurrency": 1}).json()
    assert after["download_dir"] == str(tmp_path)
    assert after["max_active_downloads"] == 2


@pytest.mark.parametrize(
    "body", [{"concurrency": 0}, {"concurrency": 65}, {"concurrency": 999}, {"quality": "fast"}]
)
def test_invalid_patch_is_422_and_changes_nothing(client: TestClient, body: dict[str, Any]) -> None:
    before = client.get("/api/v1/settings").json()
    assert client.patch("/api/v1/settings", json=body).status_code == 422
    assert client.get("/api/v1/settings").json() == before


def test_limits_follow_the_engine(client: TestClient) -> None:
    limits = client.get("/api/v1/settings").json()["limits"]
    too_many = client.patch("/api/v1/settings", json={"concurrency": limits["max_concurrency"] + 1})
    assert too_many.status_code == 422
    top = client.patch("/api/v1/settings", json={"concurrency": limits["max_concurrency"]})
    assert top.json()["concurrency"] == limits["max_concurrency"]
