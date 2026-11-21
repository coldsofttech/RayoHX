import threading
from pathlib import Path

import httpx
import pytest

from rayohx import EncryptionInfo, EncryptionMethod
from rayohx._crypto import (
    KeyProvider,
)
from rayohx._crypto._keys import MAX_CACHED_KEYS
from rayohx._http import HttpClient
from rayohx.config import NetworkConfig
from rayohx.errors import (
    AuthenticationError,
    DecryptionError,
    InvalidResponseError,
)
from tests.helpers.crypto import ENCRYPTION
from tests.helpers.media import BASE, KEY


class KeyServer:
    def __init__(self, key: bytes = KEY, status: int = 200) -> None:
        self.key = key
        self.status = status
        self.requests: list[httpx.Request] = []
        self.lock = threading.Lock()

    def __call__(self, request: httpx.Request) -> httpx.Response:
        with self.lock:
            self.requests.append(request)
        return httpx.Response(self.status, content=self.key)


def provider(server: KeyServer, max_keys: int = MAX_CACHED_KEYS) -> KeyProvider:
    client = HttpClient(
        NetworkConfig(retries=0), origin_url=BASE, transport=httpx.MockTransport(server)
    )
    return KeyProvider(client, max_keys=max_keys)


def test_a_key_is_fetched_once_and_cached() -> None:
    server = KeyServer()
    keys = provider(server)
    assert keys.key_for(ENCRYPTION) == KEY
    assert keys.key_for(ENCRYPTION) == KEY
    assert len(server.requests) == 1


def test_threads_asking_for_one_key_cause_one_request() -> None:
    server = KeyServer()
    keys = provider(server)
    threads = [threading.Thread(target=keys.key_for, args=(ENCRYPTION,)) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(server.requests) == 1


def test_a_key_of_the_wrong_size_is_rejected() -> None:
    with pytest.raises(InvalidResponseError, match="16 bytes") as info:
        provider(KeyServer(key=b"not-a-16-byte-key-0123")).key_for(ENCRYPTION)
    assert info.value.hint


def test_a_refused_key_request_suggests_credential_hosts() -> None:
    with pytest.raises(AuthenticationError) as info:
        provider(KeyServer(status=403)).key_for(ENCRYPTION)
    assert "credential_hosts" in (info.value.hint or "")


def test_the_cache_is_bounded() -> None:
    server = KeyServer()
    keys = provider(server, max_keys=2)
    for name in ("a", "b", "c"):
        keys.key_for(EncryptionInfo(EncryptionMethod.AES_128, BASE + name))
    keys.key_for(EncryptionInfo(EncryptionMethod.AES_128, BASE + "a"))
    assert len(server.requests) == 4


def test_a_missing_key_address_is_an_error() -> None:
    info = EncryptionInfo.__new__(EncryptionInfo)
    object.__setattr__(info, "method", EncryptionMethod.AES_128)
    object.__setattr__(info, "uri", None)
    with pytest.raises(DecryptionError, match="no address"):
        provider(KeyServer()).key_for(info)


# --- other kinds of address and a custom fetcher -------------------------------------------


def plain_client() -> HttpClient:
    transport = httpx.MockTransport(KeyServer())
    return HttpClient(NetworkConfig(), origin_url=BASE, transport=transport)


def enc(uri: str) -> EncryptionInfo:
    return EncryptionInfo(method=EncryptionMethod.AES_128, uri=uri)


def test_data_addresses_hold_the_key() -> None:
    import base64

    keys = provider(KeyServer())
    encoded = base64.b64encode(KEY).decode()
    assert keys.key_for(enc(f"data:text/plain;base64,{encoded}")) == KEY
    with pytest.raises(DecryptionError, match="not valid"):
        keys.key_for(enc("data:;base64,@@@"))


def test_file_keys_need_permission(tmp_path: Path) -> None:
    path = tmp_path / "k.key"
    path.write_bytes(KEY)
    client = HttpClient(
        NetworkConfig(), origin_url=BASE, transport=httpx.MockTransport(KeyServer())
    )
    refused = KeyProvider(client)
    with pytest.raises(DecryptionError) as info:
        refused.key_for(enc(path.as_uri()))
    assert "allow_file_keys" in (info.value.hint or "")
    allowed = KeyProvider(client, allow_file_keys=True)
    assert allowed.key_for(enc(path.as_uri())) == KEY
    with pytest.raises(DecryptionError, match="cannot be read"):
        allowed.key_for(enc((tmp_path / "missing").as_uri()))


def test_other_schemes_need_a_fetcher() -> None:
    with pytest.raises(DecryptionError) as info:
        provider(KeyServer()).key_for(enc("skd://something"))
    assert "key_fetcher" in (info.value.hint or "")
    client = HttpClient(
        NetworkConfig(), origin_url=BASE, transport=httpx.MockTransport(KeyServer())
    )
    seen: list[str] = []

    def fetch(uri: str) -> bytes:
        seen.append(uri)
        return KEY

    keys = KeyProvider(client, fetcher=fetch)
    assert keys.key_for(enc("vault://abc")) == KEY
    assert keys.key_for(enc("vault://abc")) == KEY  # cached
    assert seen == ["vault://abc"]


def test_a_failing_fetcher_is_explained_and_a_wrong_size_refused() -> None:
    client = HttpClient(
        NetworkConfig(), origin_url=BASE, transport=httpx.MockTransport(KeyServer())
    )

    def boom(_uri: str) -> bytes:
        raise RuntimeError("vault is sealed")

    with pytest.raises(DecryptionError, match="key_fetcher") as info:
        KeyProvider(client, fetcher=boom).key_for(enc("x://y"))
    assert "vault is sealed" in (info.value.hint or "")
    with pytest.raises(InvalidResponseError, match="16 bytes"):
        KeyProvider(client, fetcher=lambda _u: b"short").key_for(enc("x://y"))
