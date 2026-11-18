"""File names made from a template, as profiles use them.

A template is text and tokens (see ``rayohx.naming``). The platform adds ``{job}`` and
``{profile}`` to the engine's ``{name}``, ``{title}``, ``{language}``, ``{date}``, ``{time}`` and
``{host}``. The first group is known when a job is queued. ``{title}`` and ``{language}`` come from
the stream itself, so they are filled in by the engine when the download starts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rayohx.naming import (
    ENGINE_TOKENS,
    MAX_LENGTH,
    render_template,
    standard_tokens,
    template_tokens,
)
from rayohx.naming import validate_template as _validate

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "DEFAULT_TEMPLATE",
    "LATE_TOKENS",
    "MAX_LENGTH",
    "TOKENS",
    "is_late",
    "render_name",
    "render_partial",
    "tokens_for",
    "validate_template",
]

TOKENS = (*ENGINE_TOKENS, "job", "profile")
#: Tokens that only the stream can supply; the engine fills them in when the download starts.
LATE_TOKENS = ("title", "language")
DEFAULT_TEMPLATE = "{name}"
_OPEN, _CLOSE = "\ue000", "\ue001"


def validate_template(template: str) -> None:
    """Raise ``ConfigurationError`` unless ``template`` uses only known tokens."""
    _validate(template, TOKENS)


def is_late(template: str) -> bool:
    """Whether the template needs something only the stream can tell."""
    return any(token in LATE_TOKENS for token in template_tokens(template))


def render_name(template: str, tokens: Mapping[str, str]) -> str:
    """Fill in ``template`` completely."""
    return render_template(template, tokens, TOKENS)


def render_partial(template: str, tokens: Mapping[str, str]) -> str:
    """Fill in everything but the late tokens, which are kept for the engine to fill in."""
    marked = {t: f"{_OPEN}{t}{_CLOSE}" for t in LATE_TOKENS}
    rendered = render_template(template, {**tokens, **marked}, TOKENS)
    for token in LATE_TOKENS:
        rendered = rendered.replace(f"{_OPEN}{token}{_CLOSE}", "{" + token + "}")
    return rendered


def tokens_for(
    *, url: str, job_id: str, profile: str, moment: float | None = None
) -> dict[str, str]:
    """The values of every token that is known when a job is queued."""
    return {**standard_tokens(url=url, moment=moment), "job": job_id, "profile": profile}
