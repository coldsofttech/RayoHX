"""File names made from a template.

A template such as ``{profile}/{name} {date}`` is not allowed to contain folders. What it can
contain is fixed text and these tokens:

========== ==============================================================
``name``    the last meaningful part of the address (``master.m3u8`` is skipped)
``date``    the day the job was queued, ``2026-11-18``
``time``    the time it was queued, ``14-30-05``
``job``     the job's id
``profile`` the profile's name
``host``    the address's host name
========== ==============================================================

The result is deterministic (the same input always gives the same name), safe on every
operating system, and never longer than ``MAX_LENGTH``.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from rayohx.errors import ConfigurationError
from rayohx.naming import name_from_url

if TYPE_CHECKING:
    from collections.abc import Mapping

TOKENS = ("name", "date", "time", "job", "profile", "host")
MAX_LENGTH = 120
DEFAULT_TEMPLATE = "{name}"

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
    cleaned = _SPACES.sub(" ", cleaned).strip(" ._")
    return cleaned


def validate_template(template: str) -> None:
    """Raise ``ConfigurationError`` unless ``template`` uses only known tokens."""
    if not template.strip():
        raise ConfigurationError("The naming template must not be empty.")
    leftovers = _TOKEN.sub("", template)
    if "{" in leftovers or "}" in leftovers:
        raise ConfigurationError(
            f"The naming template {template!r} has a brace that is not part of a token.",
            hint=f"Use only these tokens: {', '.join('{' + t + '}' for t in TOKENS)}.",
        )
    for token in _TOKEN.findall(template):
        if token not in TOKENS:
            raise ConfigurationError(
                f"{{{token}}} is not a naming token.",
                hint=f"Use one of: {', '.join('{' + t + '}' for t in TOKENS)}.",
            )
    if re.search(r"[\\/]", template):
        raise ConfigurationError(
            "A naming template cannot contain folders.",
            hint="Set the output folder separately; the template names the file only.",
        )


def render_name(template: str, tokens: Mapping[str, str]) -> str:
    """Fill in ``template``. Raises ``ConfigurationError`` if the result would be empty."""
    validate_template(template)
    filled = _TOKEN.sub(lambda m: safe_text(tokens.get(m.group(1), "")), template)
    name = safe_text(filled)[:MAX_LENGTH].strip(" ._")
    if not name:
        raise ConfigurationError(
            f"The naming template {template!r} gives an empty name for this download."
        )
    if name.split(".")[0].lower() in _RESERVED:
        name = f"_{name}"
    return name


def tokens_for(
    *, url: str, job_id: str, profile: str, moment: float | None = None
) -> dict[str, str]:
    """The values of every token for a download."""
    when = time.localtime(time.time() if moment is None else moment)
    return {
        "name": name_from_url(url),
        "date": time.strftime("%Y-%m-%d", when),
        "time": time.strftime("%H-%M-%S", when),
        "job": job_id,
        "profile": profile,
        "host": (urlsplit(url).hostname or "").lower(),
    }
