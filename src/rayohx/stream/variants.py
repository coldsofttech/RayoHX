"""Choosing the video variant."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rayohx.stream._ranking import best_key, closest_to, describe, is_audio_only, worst_key
from rayohx.stream.quality import quality_height

if TYPE_CHECKING:
    from collections.abc import Sequence

    from rayohx.config import SelectionConfig
    from rayohx.models import Variant

#: Height that ``quality="auto"`` aims for: sharp, without the cost of the very largest stream.
AUTO_TARGET_HEIGHT = 1080


def select_variant(
    variants: Sequence[Variant], config: SelectionConfig, notes: list[str] | None = None
) -> Variant:
    """Choose one variant. Reasons for any fallback are appended to ``notes``.

    Raises:
        PlaylistError: If there are no variants.
    """
    notes = notes if notes is not None else []
    if not variants:
        from rayohx.errors import PlaylistError

        raise PlaylistError("The playlist lists no streams to download.")

    entries = list(enumerate(variants))
    video = [entry for entry in entries if not is_audio_only(entry[1])]
    entries = video or entries

    max_height = int(config.max_resolution[:-1]) if config.max_resolution else None
    allowed = [
        entry
        for entry in entries
        if (
            max_height is None
            or not quality_height(entry[1])
            or quality_height(entry[1]) <= max_height
        )
        and (config.max_bitrate is None or entry[1].bandwidth <= config.max_bitrate)
    ]
    if not allowed:
        chosen = min(entries, key=worst_key)[1]
        notes.append(
            "No stream fits the resolution or bitrate limit, so the smallest one "
            f"({describe(chosen)}) was chosen."
        )
        return chosen

    mode = config.quality
    if mode == "worst":
        return min(allowed, key=worst_key)[1]
    if mode == "best":
        return max(allowed, key=best_key)[1]
    target = AUTO_TARGET_HEIGHT if mode == "auto" else int(mode[:-1])
    return closest_to(allowed, target, notes)
