import ssl
from pathlib import Path

import httpx
import pytest

from rayohx._http import HttpClient
from rayohx._http._common import proxy_url
from rayohx.config import NetworkConfig, ProxyConfig
from rayohx.errors import (
    ConfigurationError,
    HTTPError,
    InvalidResponseError,
    NetworkConnectionError,
    NetworkError,
    NetworkTimeoutError,
    TLSError,
)
from tests.helpers.http import URL, Handler, make


def failing(error: Exception) -> Handler:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise error

    return handler


@pytest.mark.parametrize(
    ("error", "expected", "attempts"),
    [
        (httpx.ConnectTimeout("slow"), NetworkTimeoutError, 3),
        (httpx.ReadTimeout("slow"), NetworkTimeoutError, 3),
        (httpx.ConnectError("refused"), NetworkConnectionError, 3),
        (httpx.RemoteProtocolError("closed"), NetworkConnectionError, 3),
        (httpx.ProxyError("denied"), NetworkConnectionError, 3),
        (httpx.DecodingError("bad gzip"), InvalidResponseError, 1),
        (httpx.UnsupportedProtocol("weird"), NetworkError, 1),
    ],
)
def test_transport_errors_become_clear_errors(
    error: Exception, expected: type[NetworkError], attempts: int
) -> None:
    client, recorder, _ = make(failing(error), retries=2)
    with pytest.raises(expected):
        client.fetch_bytes(URL)
    assert len(recorder.requests) == attempts


def test_certificate_problems_are_not_retried() -> None:
    error = httpx.ConnectError("handshake failed")
    error.__cause__ = ssl.SSLCertVerificationError("self signed certificate")
    client, recorder, _ = make(failing(error), retries=3)
    with pytest.raises(TLSError) as info:
        client.fetch_bytes(URL)
    assert info.value.hint
    assert len(recorder.requests) == 1


def test_a_broken_secure_connection_is_retried() -> None:
    error = httpx.ConnectError("handshake failed")
    error.__cause__ = ssl.SSLError("EOF occurred in violation of protocol")
    client, recorder, _ = make(failing(error), retries=2)
    with pytest.raises(NetworkConnectionError) as info:
        client.fetch_bytes(URL)
    assert not isinstance(info.value, TLSError)
    assert info.value.hint
    assert len(recorder.requests) == 3


def test_error_messages_never_contain_credentials() -> None:
    url = "https://user:pw@media.example.com/a.ts?token=secret123"
    client, _, _ = make(lambda _r: httpx.Response(500), retries=0)
    with pytest.raises(HTTPError) as info:
        client.fetch_bytes(url)
    assert "pw@" not in str(info.value)
    assert "secret123" not in str(info.value)


def test_an_unreadable_certificate_file_is_a_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="certificate file"):
        HttpClient(NetworkConfig(verify_tls=tmp_path / "missing.pem"))


def test_turning_verification_off_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING", logger="rayohx"):
        HttpClient(NetworkConfig(verify_tls=False)).close()
    assert "verification is turned off" in caplog.text


def test_proxy_credentials_are_placed_in_the_proxy_address() -> None:
    plain = ProxyConfig(url="http://proxy.example:3128")
    assert proxy_url(plain) == "http://proxy.example:3128"
    secured = ProxyConfig(url="http://proxy.example:3128", username="me@work", password="p:w/d")
    assert proxy_url(secured) == "http://me%40work:p%3Aw%2Fd@proxy.example:3128"
    inline = ProxyConfig(url="http://old:old@proxy.example:3128", username="new", password="pw")
    assert proxy_url(inline) == "http://new:pw@proxy.example:3128"
