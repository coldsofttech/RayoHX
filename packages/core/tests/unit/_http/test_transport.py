"""Building the ``httpx`` client: pool, proxies, the environment and hosts that skip the proxy."""

import httpx
import pytest

from rayohx._http import HttpClient
from rayohx._http._transport import build_client, no_proxy_mounts
from rayohx.config import NetworkConfig, ProxyConfig


def test_no_proxy_mounts_cover_hosts_and_subdomains() -> None:
    mounts = no_proxy_mounts(["skip.example.com", ".internal.test", "localhost:8080"])
    assert mounts == {
        "all://skip.example.com": None,
        "all://*.skip.example.com": None,
        "all://internal.test": None,
        "all://*.internal.test": None,
        "all://localhost": None,
        "all://*.localhost": None,
    }


def test_no_proxy_star_bypasses_every_host() -> None:
    assert no_proxy_mounts(["*"]) == {"all://": None}


def test_no_proxy_ignores_ranges_and_ipv6() -> None:
    assert no_proxy_mounts(["10.0.0.0/8", "[::1]", ""]) == {}


def test_the_client_is_closed_with_its_context() -> None:
    with build_client(NetworkConfig(), pool_size=3) as client:
        assert not client.is_closed
    assert client.is_closed


def test_a_custom_transport_disables_environment_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    transport = httpx.MockTransport(lambda _request: httpx.Response(200))
    with build_client(NetworkConfig(proxy_from_env=True), pool_size=1, transport=transport) as c:
        assert not c._mounts


def test_socks_proxy_builds_a_client() -> None:
    config = NetworkConfig(proxy=ProxyConfig(url="socks5h://127.0.0.1:1"))
    HttpClient(config).close()


def test_environment_proxy_is_used_only_when_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("NO_PROXY", "skip.example.com, 10.0.0.0/8, internal:8080")
    with HttpClient(NetworkConfig()) as plain:
        assert not plain._client._mounts
    with HttpClient(NetworkConfig(proxy_from_env=True)) as from_env:
        assert len(from_env._client._mounts) >= 2  # the proxy, and the bypassed host


def test_explicit_proxy_wins_over_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://env.invalid:3128")
    config = NetworkConfig(proxy_from_env=True, proxy=ProxyConfig(url="http://mine.invalid:1"))
    with HttpClient(config) as client:
        assert len(client._client._mounts) == 1  # just the explicit proxy
