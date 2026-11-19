"""Making sure nothing secret ends up in a report.

A report is meant to be attached to a bug report or sent to someone. Three defences work together:

1. Everything is passed through the redactor: tokens in addresses, bearer tokens, cookies,
   passwords, and any value under a name like ``token`` or ``authorization``.
2. The job's own secrets (its cookies, secret headers, proxy login) and every value in the query of
   its address are searched for *literally* in every piece of text, whatever they appear next to.
3. The home folder is shown as ``~``.
"""

from __future__ import annotations

from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, quote, urlsplit

from rayohx.platform.events.model import sanitize
from rayohx.redaction import REDACTED, is_sensitive_name, redact_text

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

MIN_SECRET = 4


def secret_values(*sources: Any) -> set[str]:
    """Every string worth searching for: the values in nested secrets, and an address's query."""
    found: set[str] = set()

    def walk(item: Any) -> None:
        if isinstance(item, str):
            if len(item) >= MIN_SECRET:
                found.add(item)
        elif isinstance(item, dict):
            for value in item.values():
                walk(value)
        elif isinstance(item, list | tuple | set):
            for value in item:
                walk(value)

    for source in sources:
        walk(source)
    return found


def url_secrets(url: str) -> set[str]:
    """The user info and every query value of an address."""
    found: set[str] = set()
    try:
        parts = urlsplit(url)
    except ValueError:
        return found
    if parts.username and len(parts.username) >= MIN_SECRET:
        found.add(parts.username)
    if parts.password and len(parts.password) >= MIN_SECRET:
        found.add(parts.password)
    for _, value in parse_qsl(parts.query, keep_blank_values=False):
        if len(value) >= MIN_SECRET:
            found.add(value)
    return found


class Sanitizer:
    """Cleans nested data for a report."""

    def __init__(self, secrets: Iterable[str] = (), *, home: Path | None = None) -> None:
        variants: set[str] = set()
        for secret in secrets:
            if len(secret) >= MIN_SECRET:
                variants |= {secret, quote(secret, safe=""), quote(secret)}
        # Longest first, so a secret that contains another is removed whole.
        self._secrets = sorted(variants, key=len, reverse=True)
        self._home = str(home if home is not None else Path.home())

    def text(self, value: str) -> str:
        cleaned = redact_text(value)
        for secret in self._secrets:
            cleaned = cleaned.replace(secret, REDACTED)
        if self._home and self._home not in {"/", "."}:
            cleaned = cleaned.replace(self._home, "~")
        return cleaned

    def clean(self, value: Any) -> Any:
        """Plain JSON data with every string cleaned and every secret-named value replaced."""
        plain = sanitize(value)  # redacts, bounds, and makes everything plain data
        return self._walk(plain)

    def _walk(self, item: Any) -> Any:
        if isinstance(item, str):
            return self.text(item)
        if isinstance(item, dict):
            return {
                self.text(str(k)): REDACTED if is_sensitive_name(str(k)) else self._walk(v)
                for k, v in item.items()
            }
        if isinstance(item, list):
            return [self._walk(v) for v in item]
        if isinstance(item, PurePath):
            return self.text(str(item))
        return item


def contains_secret(data: Mapping[str, Any] | list[Any] | str, secrets: Iterable[str]) -> list[str]:
    """Which of ``secrets`` appear anywhere in ``data``. Used to prove a report is clean."""
    import json

    text = data if isinstance(data, str) else json.dumps(data, default=str)
    return [s for s in secrets if len(s) >= MIN_SECRET and s in text]
