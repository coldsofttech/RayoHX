"""Default options, saved between runs so a client does not have to repeat them."""

import contextlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

#: Proxy logins and key passwords are never written to disk. The user name goes too, because a
#: proxy with a user name and no password is not valid.
SECRET_KEYS = frozenset({"username", "password", "client_key_password"})


def default_file() -> Path:
    """The per-user file, next to the command line's settings."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "rayohx" / "api-defaults.json"


def without_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: without_secrets(v) for k, v in value.items() if k not in SECRET_KEYS}
    return value


def merge(base: dict[str, Any], top: dict[str, Any]) -> dict[str, Any]:
    """``top`` laid over ``base``, section by section."""
    result = dict(base)
    for key, value in top.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = value
    return result


class DefaultsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}
        with contextlib.suppress(OSError, ValueError):
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self._data = loaded

    def get(self) -> dict[str, Any]:
        with self._lock:
            copy: dict[str, Any] = json.loads(json.dumps(self._data))
            return copy

    def set(self, data: dict[str, Any]) -> None:
        """Keep ``data`` (without secrets) in memory and on disk."""
        cleaned = without_secrets(data)
        with self._lock:
            self._data = cleaned
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle, name = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as out:
                    json.dump(cleaned, out, indent=2, sort_keys=True)
                Path(name).replace(self.path)
            finally:
                Path(name).unlink(missing_ok=True)
