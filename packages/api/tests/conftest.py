from collections.abc import Iterator

import pytest

from rayohx_api.config import get_settings


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test in an ``integration`` folder (core, cli, api, ui) as an integration test."""
    for item in items:
        if "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(autouse=True)
def _fresh_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[None]:
    """Give every test new settings and its own platform folder, with no API key needed."""
    monkeypatch.setenv("RAYOHX_API_HOME", str(tmp_path_factory.mktemp("platform")))
    monkeypatch.setenv("RAYOHX_API_AUTH_MODE", "none")
    monkeypatch.delenv("RAYOHX_API_API_KEYS", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
