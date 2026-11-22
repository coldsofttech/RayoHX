import pytest
from pydantic import ValidationError

from rayohx_api.schemas.v1 import QUALITY, DownloadCreate, Network

URL = "https://example.test/master.m3u8"


@pytest.mark.parametrize("value", ["best", "WORST", "Auto", "720p", "1080p", "2160p"])
def test_quality_accepts(value: str) -> None:
    assert DownloadCreate(url=URL, quality=value).quality == value


@pytest.mark.parametrize("value", ["", "fast", "72p", "12345p", "720", "best ", "720px"])
def test_quality_rejects(value: str) -> None:
    with pytest.raises(ValidationError):
        DownloadCreate(url=URL, quality=value)


def test_quality_pattern_is_exported() -> None:
    assert QUALITY.startswith("(?i)")


def test_network_defaults_are_independent() -> None:
    first, second = Network(), Network()
    first.headers["X"] = "1"
    assert second.headers == {}


def test_network_header_limit() -> None:
    Network(headers={str(i): "v" for i in range(32)})
    with pytest.raises(ValidationError):
        Network(headers={str(i): "v" for i in range(33)})
