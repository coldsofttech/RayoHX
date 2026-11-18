"""Safe file names, from text, from web addresses and from templates.

A template such as ``{title} [{date}]`` is not allowed to contain folders. What it can contain is
fixed text and tokens. The result is deterministic (the same input always gives the same name),
safe on every operating system, and never longer than ``MAX_LENGTH``.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from rayohx._download._output._names import MAX_NAME_LENGTH, name_from_url, sanitize_filename
from rayohx.errors import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

__all__ = [
    "ENGINE_TOKENS",
    "MAX_LENGTH",
    "MAX_NAME_LENGTH",
    "name_from_url",
    "render_template",
    "safe_text",
    "sanitize_filename",
    "template_tokens",
    "validate_template",
]

#: Tokens the engine can fill in for a download.
ENGINE_TOKENS = ("name", "title", "language", "date", "time", "host")
MAX_LENGTH = 120

_TOKEN = re.compile(r"\{([^{}]*)\}")
_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]+')
_SPACES = re.compile(r"\s+")
_RESERVED = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{n}" for n in range(1, 10)),
        *(f"lpt{n}" for n in range(1, 10)),
    }
)


def safe_text(value: str) -> str:
    """Make ``value`` safe to use as part of a file name on every system."""
    cleaned = _FORBIDDEN.sub("_", value)
    return _SPACES.sub(" ", cleaned).strip(" ._")


def template_tokens(template: str) -> list[str]:
    """The tokens a template uses, in order."""
    return _TOKEN.findall(template)


def validate_template(template: str, allowed: Collection[str] = ENGINE_TOKENS) -> None:
    """Raise ``ConfigurationError`` unless ``template`` uses only the ``allowed`` tokens."""
    shown = ", ".join("{" + t + "}" for t in allowed)
    if not template.strip():
        raise ConfigurationError("The naming template must not be empty.")
    if "{" in _TOKEN.sub("", template) or "}" in _TOKEN.sub("", template):
        raise ConfigurationError(
            f"The naming template {template!r} has a brace that is not part of a token.",
            hint=f"Use only these tokens: {shown}.",
        )
    for token in template_tokens(template):
        if token not in allowed:
            raise ConfigurationError(
                f"{{{token}}} is not a naming token.", hint=f"Use one of: {shown}."
            )
    if re.search(r"[\\/]", template):
        raise ConfigurationError(
            "A naming template cannot contain folders.",
            hint="Set the output folder separately; the template names the file only.",
        )


def render_template(
    template: str, tokens: Mapping[str, str], allowed: Collection[str] = ENGINE_TOKENS
) -> str:
    """Fill in ``template``. Raises ``ConfigurationError`` if the result would be empty."""
    validate_template(template, allowed)
    filled = _TOKEN.sub(lambda m: safe_text(tokens.get(m.group(1), "")), template)
    name = safe_text(filled)[:MAX_LENGTH].strip(" ._")
    if not name:
        raise ConfigurationError(
            f"The naming template {template!r} gives an empty name for this download."
        )
    if name.split(".")[0].lower() in _RESERVED:
        name = f"_{name}"
    return name


def standard_tokens(
    *, url: str, title: str | None = None, language: str | None = None, moment: float | None = None
) -> dict[str, str]:
    """The values of the engine's tokens for a download."""
    when = time.localtime(time.time() if moment is None else moment)
    name = name_from_url(url)
    return {
        "name": name,
        "title": title or name,
        "language": language or "",
        "date": time.strftime("%Y-%m-%d", when),
        "time": time.strftime("%H-%M-%S", when),
        "host": (urlsplit(url).hostname or "").lower(),
    }
