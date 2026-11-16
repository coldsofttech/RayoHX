"""Fetching decryption keys through the HTTP layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rayohx._crypto._cipher import KEY_SIZE
from rayohx.errors import AuthenticationError, DecryptionError, InvalidResponseError

if TYPE_CHECKING:
    from rayohx._http import HttpClient
    from rayohx.models import EncryptionInfo

MAX_CACHED_KEYS = 64


class KeyProvider:
    """Fetches decryption keys once each and keeps them for the rest of the download."""

    def __init__(self, client: HttpClient, *, max_keys: int = MAX_CACHED_KEYS) -> None:
        import threading

        self._client = client
        self._max_keys = max_keys
        self._keys: dict[str, bytes] = {}
        self._lock = threading.Lock()

    def key_for(self, encryption: EncryptionInfo) -> bytes:
        """Return the 16-byte key for ``encryption``, fetching it on first use."""
        uri = encryption.uri
        if not uri:
            raise DecryptionError("The playlist gives no address for the key.")
        with self._lock:
            cached = self._keys.get(uri)
            if cached is not None:
                return cached
            try:
                response = self._client.fetch_bytes(uri, max_bytes=1024)
            except AuthenticationError as exc:
                raise AuthenticationError(
                    uri,
                    exc.status_code,
                    hint="The key server refused the request. If it needs your Authorization "
                    "header or cookies, add its host to credential_hosts.",
                ) from exc
            key = response.content
            if len(key) != KEY_SIZE:
                raise InvalidResponseError(
                    f"The key must be {KEY_SIZE} bytes but {len(key)} were received.",
                    hint="The key server may have sent an error page or a protected (DRM) key.",
                )
            if len(self._keys) >= self._max_keys:
                self._keys.pop(next(iter(self._keys)))
            self._keys[uri] = key
            return key
