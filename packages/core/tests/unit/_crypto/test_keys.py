import threading

import httpx
import pytest

from rayohx import EncryptionInfo, EncryptionMethod
from rayohx._crypto import (
    KeyProvider,
)
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


def provider(server: KeyServer, **options: int) -> KeyProvider:
    client = HttpClient(
        NetworkConfig(retries=0), origin_url=BASE, transport=httpx.MockTransport(server)
    )
    return KeyProvider(client, **options)


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
