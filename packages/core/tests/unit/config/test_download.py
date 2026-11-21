from pathlib import Path

import pytest

from rayohx import StorageStrategy
from rayohx.config import DownloadConfig, NetworkConfig, ProxyConfig
from rayohx.errors import ConfigurationError


def test_defaults_are_valid_and_conservative() -> None:
    config = DownloadConfig()
    assert config.concurrency == 4
    assert config.resume
    assert config.storage.strategy is StorageStrategy.AUTO
    assert not config.output.overwrite
    assert config.network.verify_tls is True


def test_configs_are_immutable() -> None:
    with pytest.raises(AttributeError):
        DownloadConfig().concurrency = 9  # type: ignore[misc]


@pytest.mark.parametrize("value", [0, 65, -1])
def test_concurrency_is_bounded(value: int) -> None:
    with pytest.raises(ConfigurationError):
        DownloadConfig(concurrency=value)


def test_as_dict_never_contains_secrets() -> None:
    config = DownloadConfig(
        network=NetworkConfig(
            headers={"Authorization": "Bearer topsecret", "Referer": "https://r"},
            cookies={"session": "cookiesecret"},
            proxy=ProxyConfig(url="http://p:1", username="u", password="proxysecret"),
            verify_tls=Path("/ca.pem"),
        ),
    )
    dump = str(config.as_dict())
    for secret in ("topsecret", "cookiesecret", "proxysecret"):
        assert secret not in dump
        assert secret not in repr(config)
    assert "https://r" in dump
    assert "ca.pem" in dump


def test_key_options_default_to_off_and_show_only_whether_they_are_set() -> None:
    config = DownloadConfig()
    assert config.key_fetcher is None
    assert not config.allow_file_keys
    assert config.as_dict()["key_fetcher"] is False
    assert config.as_dict()["allow_file_keys"] is False

    def fetcher(uri: str) -> bytes:
        return b"0" * 16

    custom = DownloadConfig(key_fetcher=fetcher, allow_file_keys=True)
    assert custom.as_dict()["key_fetcher"] is True
    assert custom.as_dict()["allow_file_keys"] is True
    assert "fetcher" not in repr(custom)
