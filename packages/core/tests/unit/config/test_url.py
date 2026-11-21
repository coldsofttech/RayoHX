import pytest

from rayohx.config.url import validate_url
from rayohx.errors import ConfigurationError


@pytest.mark.parametrize(
    "url", ["https://example.com/a.m3u8", "http://host:8080/x?y=1", "  https://example.com/a  "]
)
def test_validate_url_accepts_http(url: str) -> None:
    assert validate_url(url) == url.strip()


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://host/a",
        "file:///etc/passwd",
        "/local/path.m3u8",
        "https://",
        "http://[::1",
        "https://h/a\nb",
    ],
)
def test_validate_url_rejects_the_rest(url: str) -> None:
    with pytest.raises(ConfigurationError):
        validate_url(url)
