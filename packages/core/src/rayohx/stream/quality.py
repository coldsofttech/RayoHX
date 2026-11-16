"""How big a stream's picture is."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rayohx.models import Variant


def quality_height(variant: Variant) -> int:
    """Picture size as a "p" number: the shorter side, so portrait video is judged fairly."""
    if variant.resolution is None:
        return 0
    return min(variant.resolution.width, variant.resolution.height)
