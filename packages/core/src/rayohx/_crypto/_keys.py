"""Fetching decryption keys through the HTTP layer."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote_to_bytes, urlsplit
from urllib.request import url2pathname

from rayohx._crypto._cipher import KEY_SIZE
from rayohx.errors import (
    AuthenticationError,
    DecryptionError,
    InvalidResponseError,
    RayoHXError,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from rayohx._http import HttpClient
    from rayohx.models import EncryptionInfo

MAX_CACHED_KEYS = 64


class KeyProvider:
    """Fetches decryption keys once each and keeps them for the rest of the download."""

    def __init__(
        self,
        client: HttpClient,
        *,
        max_keys: int = MAX_CACHED_KEYS,
        fetcher: Callable[[str], bytes] | None = None,
        allow_file_keys: bool = False,
    ) -> None:
        import threading

        self._client = client
        self._fetcher = fetcher
        self._allow_file_keys = allow_file_keys
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
            key = self._fetch(uri)
            if len(key) != KEY_SIZE:
                raise InvalidResponseError(
                    f"The key must be {KEY_SIZE} bytes but {len(key)} were received.",
                    hint="The key server may have sent an error page or a protected (DRM) key.",
                )
            if len(self._keys) >= self._max_keys:
                self._keys.pop(next(iter(self._keys)))
            self._keys[uri] = key
            return key

    def _fetch(self, uri: str) -> bytes:
        if self._fetcher is not None:
            try:
                return bytes(self._fetcher(uri))
            except RayoHXError:
                raise
            except Exception as exc:
                raise DecryptionError(
                    "Your key_fetcher failed.", hint=f"{type(exc).__name__}: {exc}"
                ) from exc
        scheme = urlsplit(uri).scheme.lower()
        if scheme == "data":
            return _data_key(uri)
        if scheme == "file":
            return self._file_key(uri)
        if scheme not in ("http", "https"):
            raise DecryptionError(
                f"Keys at {scheme or 'this kind of'!s} addresses cannot be fetched.",
                hint="Give the config a key_fetcher that returns the key for this address.",
            )
        try:
            return self._client.fetch_bytes(uri, max_bytes=1024).content
        except AuthenticationError as exc:
            raise AuthenticationError(
                uri,
                exc.status_code,
                hint="The key server refused the request. If it needs your Authorization "
                "header or cookies, add its host to credential_hosts.",
            ) from exc

    def _file_key(self, uri: str) -> bytes:
        if not self._allow_file_keys:
            raise DecryptionError(
                "The playlist points to a key on this machine.",
                hint="Local key files are off by default. Set allow_file_keys "
                "(--allow-file-keys) if you trust this stream.",
            )
        path = Path(url2pathname(urlsplit(uri).path))
        try:
            with path.open("rb") as handle:
                return handle.read(KEY_SIZE + 1)
        except OSError as exc:
            raise DecryptionError(f"The key file {path} cannot be read.") from exc


def _data_key(uri: str) -> bytes:
    """The bytes inside a ``data:`` address (``data:;base64,...`` or percent-encoded)."""
    header, _, payload = uri.partition(",")
    try:
        if header.lower().endswith(";base64"):
            return base64.b64decode(payload, validate=True)
        return unquote_to_bytes(payload)
    except ValueError as exc:
        raise DecryptionError("The key inside the playlist is not valid.") from exc
