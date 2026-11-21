import pytest

from rayohx.config import ProxyConfig
from rayohx.errors import ConfigurationError


def test_proxy_requires_http_scheme() -> None:
    assert ProxyConfig(url="http://proxy:3128").url == "http://proxy:3128"
    with pytest.raises(ConfigurationError, match=r"SOCKS|http"):
        ProxyConfig(url="ftp://proxy:21")
    with pytest.raises(ConfigurationError) as info:
        ProxyConfig(url="socks4://proxy:1080")
    assert "SOCKS4" in (info.value.hint or "")
    with pytest.raises(ConfigurationError):
        ProxyConfig(url="http://[bad")


def test_proxy_credentials_come_in_pairs_and_stay_hidden() -> None:
    with pytest.raises(ConfigurationError):
        ProxyConfig(url="http://p:1", username="u")
    proxy = ProxyConfig(url="http://u:pw@p:1", username="u", password="pw")
    assert "pw" not in repr(proxy)
    assert "pw" not in str(proxy.as_dict())
    assert proxy.redacted_url == "http://***@p:1"


@pytest.mark.parametrize("scheme", ["socks5", "socks5h"])
def test_socks5_proxies_are_accepted(scheme: str) -> None:
    assert ProxyConfig(url=f"{scheme}://proxy:1080").url == f"{scheme}://proxy:1080"
