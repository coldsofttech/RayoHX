import json
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from rayohx_api.auth import Principal, authenticate
from rayohx_api.config import get_settings
from rayohx_api.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_health_and_ready(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    body = client.get("/ready").json()
    assert body["status"] == "ready"
    assert body["version"]


class Item(BaseModel):
    name: str


def test_invalid_body_lists_errors() -> None:
    app = create_app()

    @app.post("/items")
    def create_item(body: Item) -> Item:
        return body

    response = TestClient(app).post("/items", json={})

    assert response.status_code == 422
    assert response.json()["errors"]


def test_request_id_is_reused_or_created(client: TestClient) -> None:
    assert client.get("/health", headers={"X-Request-ID": "abc"}).headers["X-Request-ID"] == "abc"
    assert client.get("/health").headers["X-Request-ID"]


def test_security_headers(client: TestClient) -> None:
    response = client.get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "Cache-Control" not in response.headers
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_api_responses_are_not_cached() -> None:
    app = create_app()

    @app.get("/api/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    response = TestClient(app).get("/api/ping")

    assert response.headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_hsts_only_over_https() -> None:
    https = TestClient(create_app(), base_url="https://testserver")

    assert "Strict-Transport-Security" in https.get("/health").headers
    assert "Strict-Transport-Security" not in TestClient(create_app()).get("/health").headers


def test_docs_are_hidden_by_default(client: TestClient) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_docs_can_be_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAYOHX_API_DOCS_ENABLED", "true")
    get_settings.cache_clear()

    docs = TestClient(create_app())

    assert docs.get("/openapi.json").status_code == 200
    assert "default-src 'none'" not in docs.get("/docs").headers.get("Content-Security-Policy", "")


def test_oversized_body_is_413(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAYOHX_API_MAX_BODY_BYTES", "10")
    get_settings.cache_clear()

    app = create_app()

    @app.post("/items")
    def create_item(body: Item) -> Item:
        return body

    response = TestClient(app).post("/items", json={"name": "A" * 50})

    assert response.status_code == 413


def test_unexpected_errors_do_not_leak_details() -> None:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret detail")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert "secret" not in response.text
    assert json.loads(response.text)["title"] == "Internal Server Error"


def test_cors_allows_configured_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAYOHX_API_CORS_ORIGINS", '["https://app.example.com"]')
    get_settings.cache_clear()

    response = TestClient(create_app()).get(
        "/health", headers={"Origin": "https://app.example.com"}
    )

    assert response.headers["access-control-allow-origin"] == "https://app.example.com"


def _app_with_whoami(*, embedded: bool = False) -> FastAPI:
    app = create_app(embedded=embedded)

    @app.get("/whoami")
    def whoami(principal: Annotated[Principal, Depends(authenticate)]) -> dict[str, str]:
        return {"subject": principal.subject, "method": principal.method}

    return app


class TestAuth:
    @pytest.fixture(autouse=True)
    def _api_key_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAYOHX_API_AUTH_MODE", "api_key")
        monkeypatch.setenv("RAYOHX_API_API_KEYS", '["s3cret"]')
        get_settings.cache_clear()

    def test_whoami_needs_a_valid_key(self) -> None:
        client = TestClient(_app_with_whoami())

        missing = client.get("/whoami")
        wrong = client.get("/whoami", headers={"X-API-Key": "nope"})
        valid = client.get("/whoami", headers={"X-API-Key": "s3cret"})

        assert missing.status_code == wrong.status_code == 401
        assert missing.headers["WWW-Authenticate"] == "ApiKey"
        assert valid.json() == {"subject": "api-key", "method": "api_key"}

    def test_standalone_app_refuses_to_start_without_a_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("RAYOHX_API_API_KEYS")
        get_settings.cache_clear()

        with pytest.raises(ValueError, match="RAYOHX_API_API_KEYS"):
            create_app()

    def test_embedded_app_trusts_cornea_instead(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("RAYOHX_API_API_KEYS")
        get_settings.cache_clear()

        response = TestClient(_app_with_whoami(embedded=True)).get("/whoami")

        assert response.json() == {"subject": "cornea-session", "method": "cornea"}

    def test_auth_can_be_switched_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RAYOHX_API_AUTH_MODE", "none")
        get_settings.cache_clear()

        response = TestClient(_app_with_whoami()).get("/whoami")

        assert response.json() == {"subject": "anonymous", "method": "none"}
