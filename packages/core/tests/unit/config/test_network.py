from pathlib import Path

import pytest

from rayohx.config import NetworkConfig
from rayohx.errors import ConfigurationError


def test_network_headers_are_validated_and_frozen() -> None:
    source = {"Referer": "https://r"}
    network = NetworkConfig(headers=source)
    source["Referer"] = "changed"
    assert network.headers["Referer"] == "https://r"
    with pytest.raises(TypeError):
        network.headers["X"] = "y"  # type: ignore[index]
    with pytest.raises(ConfigurationError):
        NetworkConfig(headers={"Bad Name": "x"})
    with pytest.raises(ConfigurationError):
        NetworkConfig(headers={"X-Ok": "line\r\nInjected: 1"})


def test_network_cookie_and_agent_validation() -> None:
    with pytest.raises(ConfigurationError):
        NetworkConfig(cookies={"a": "b; c=d"})
    with pytest.raises(ConfigurationError):
        NetworkConfig(user_agent="  ")
    with pytest.raises(ConfigurationError):
        NetworkConfig(user_agent="x\ny")


@pytest.mark.parametrize(
    "field",
    [
        {"connect_timeout": 0},
        {"read_timeout": -1},
        {"total_timeout": 0},
        {"rate_limit": 0},
        {"retries": -1},
        {"backoff_factor": -0.1},
        {"max_redirects": -1},
    ],
)
def test_network_numbers_are_checked(field: dict[str, float]) -> None:
    with pytest.raises(ConfigurationError):
        NetworkConfig(**field)  # type: ignore[arg-type]


def test_request_headers_let_user_values_win() -> None:
    network = NetworkConfig(user_agent="Agent/1", headers={"user-agent": "Mine", "Origin": "o"})
    headers = network.request_headers()
    assert headers == {"user-agent": "Mine", "Origin": "o"}
    assert NetworkConfig(user_agent="Agent/1").request_headers() == {"User-Agent": "Agent/1"}


def test_credential_hosts_are_validated_and_lowercased() -> None:
    network = NetworkConfig(credential_hosts=("CDN.Example.com", "localhost"))
    assert network.credential_hosts == ("cdn.example.com", "localhost")
    assert network.as_dict()["credential_hosts"] == ["cdn.example.com", "localhost"]
    for bad in ("https://cdn.example.com", "cdn.example.com/path", "a b", "", "-bad.com"):
        with pytest.raises(ConfigurationError, match="host name"):
            NetworkConfig(credential_hosts=(bad,))


def test_network_client_key_needs_a_certificate() -> None:
    with pytest.raises(ConfigurationError):
        NetworkConfig(client_key=Path("client.key"))
    with pytest.raises(ConfigurationError):
        NetworkConfig(client_key_password="secret")
    NetworkConfig(client_cert=Path("client.pem"), client_key=Path("client.key"))


def test_network_as_dict_hides_the_client_key_password() -> None:
    network = NetworkConfig(client_cert=Path("client.pem"), client_key_password="secret")
    data = network.as_dict()
    assert "secret" not in str(data)
    assert "secret" not in repr(network)
    assert data["client_key_password"] != "secret"
    assert data["proxy_from_env"] is False
