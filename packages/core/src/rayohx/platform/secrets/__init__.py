"""Where the secrets of queued jobs are kept.

A queued job must survive a restart, but its headers, cookies and proxy passwords must never be
written to the database, the logs or an export. The database holds only a *reference*; the secret
values live in a ``SecretStore``:

* ``KeyringSecretStore``: the operating system's credential store, through the optional
  ``keyring`` package (``pip install keyring``).
* ``MemorySecretStore``: this process only. Jobs that need secrets are marked
  ``needs_credentials`` after a restart instead of failing mysteriously, and wait until the
  secrets are supplied again.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Protocol

SERVICE = "rayohx"


class SecretStore(Protocol):
    """Keeps named bundles of secrets."""

    #: Whether secrets survive a restart of the program.
    persistent: bool

    def get(self, ref: str) -> dict[str, Any] | None: ...

    def put(self, ref: str, secrets: dict[str, Any]) -> None: ...

    def delete(self, ref: str) -> None: ...


class MemorySecretStore:
    """Keeps secrets in memory only."""

    persistent = False

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._lock = threading.Lock()

    def get(self, ref: str) -> dict[str, Any] | None:
        with self._lock:
            text = self._data.get(ref)
        return None if text is None else json.loads(text)

    def put(self, ref: str, secrets: dict[str, Any]) -> None:
        with self._lock:
            self._data[ref] = json.dumps(secrets)

    def delete(self, ref: str) -> None:
        with self._lock:
            self._data.pop(ref, None)


class KeyringSecretStore:
    """Keeps secrets in the operating system's credential store."""

    persistent = True

    def __init__(self, service: str = SERVICE) -> None:
        import keyring  # optional dependency

        self._keyring = keyring
        self._service = service

    def get(self, ref: str) -> dict[str, Any] | None:
        text = self._keyring.get_password(self._service, ref)
        return None if text is None else json.loads(text)

    def put(self, ref: str, secrets: dict[str, Any]) -> None:
        self._keyring.set_password(self._service, ref, json.dumps(secrets))

    def delete(self, ref: str) -> None:
        import contextlib

        with contextlib.suppress(Exception):  # already gone, or the backend refuses
            self._keyring.delete_password(self._service, ref)


def default_secret_store() -> SecretStore:
    """The credential store when ``keyring`` has a working backend, else memory."""
    try:
        import keyring
        from keyring.backends import fail

        if isinstance(keyring.get_keyring(), fail.Keyring):
            return MemorySecretStore()
        return KeyringSecretStore()
    except Exception:
        return MemorySecretStore()


__all__ = [
    "KeyringSecretStore",
    "MemorySecretStore",
    "SecretStore",
    "default_secret_store",
]
