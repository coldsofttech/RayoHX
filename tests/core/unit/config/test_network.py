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
