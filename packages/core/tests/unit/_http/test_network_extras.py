"""SOCKS proxies, proxies from the environment and client certificates."""

import datetime
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from rayohx._http import HttpClient
from rayohx._http._common import environment_proxies, tls_context
from rayohx.config import NetworkConfig, ProxyConfig
from rayohx.errors import ConfigurationError


def make_identity(directory: Path, password: bytes | None = None) -> tuple[Path, Path]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "client")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_path = directory / "client.pem"
    key_path = directory / "client.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    encryption = (
        serialization.BestAvailableEncryption(password)
        if password
        else serialization.NoEncryption()
    )
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, encryption)
    )
    return cert_path, key_path


def test_socks_proxy_builds_a_client() -> None:
    config = NetworkConfig(proxy=ProxyConfig(url="socks5h://127.0.0.1:1"))
    HttpClient(config).close()


def test_environment_proxies_are_read_by_scheme() -> None:
    env = {
        "HTTPS_PROXY": "http://secure:3128",
        "http_proxy": "proxy:8080",
        "ALL_PROXY": "ftp://nope",
        "NO_PROXY": "localhost, .internal.example.com",
    }
    proxies, no_proxy = environment_proxies(env)
    assert proxies["https"].url == "http://secure:3128"
    assert proxies["http"].url == "http://proxy:8080"
    assert "all" not in proxies
    assert no_proxy == ("localhost", ".internal.example.com")


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


def test_client_certificate_is_loaded(tmp_path: Path) -> None:
    cert, key = make_identity(tmp_path)
    assert tls_context(True, cert, key) is not True
    HttpClient(NetworkConfig(client_cert=cert, client_key=key)).close()


def test_client_certificate_with_password_and_verification_off(tmp_path: Path) -> None:
    cert, key = make_identity(tmp_path, b"secret")
    context = tls_context(False, cert, key, "secret")
    assert not context.check_hostname  # type: ignore[union-attr]
    with pytest.raises(ConfigurationError, match="client certificate"):
        tls_context(True, cert, key, "wrong")


def test_unreadable_client_certificate_is_a_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="client certificate"):
        tls_context(True, tmp_path / "missing.pem")


def test_client_key_needs_a_certificate_and_password_stays_hidden(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="client certificate"):
        NetworkConfig(client_key=tmp_path / "k")
    config = NetworkConfig(client_cert=tmp_path / "c", client_key_password="hunter2")
    assert "hunter2" not in repr(config)
    assert "hunter2" not in str(config.as_dict())
