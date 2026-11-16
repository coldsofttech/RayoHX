"""Ordering variants from best to worst."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rayohx.stream.quality import quality_height

if TYPE_CHECKING:
    from rayohx.models import Variant

_VIDEO_PREFIXES = ("avc", "hvc", "hev", "vp0", "av01", "dvh", "dvav", "mp4v")
#: Codec families from most to least widely playable. Only breaks ties between equal streams.
_CODEC_RANKS = (("avc", 4), ("hvc", 3), ("hev", 3), ("vp0", 2), ("av01", 1))


def codec_rank(variant: Variant) -> int:
    for codec in variant.codecs:
        lowered = codec.lower()
        for prefix, rank in _CODEC_RANKS:
            if lowered.startswith(prefix):
                return rank
    return 0


def is_audio_only(variant: Variant) -> bool:
    if variant.resolution is not None or not variant.codecs:
        return False
    return not any(codec.lower().startswith(_VIDEO_PREFIXES) for codec in variant.codecs)


def best_key(entry: tuple[int, Variant]) -> tuple[int, int, int, float, int, int]:
    index, variant = entry
    return (
        quality_height(variant),
        variant.bandwidth,
        variant.average_bandwidth or 0,
        variant.frame_rate or 0.0,
        codec_rank(variant),
        -index,  # equal streams: the one listed first wins
    )


def worst_key(entry: tuple[int, Variant]) -> tuple[int, int, int]:
    index, variant = entry
    return (quality_height(variant), variant.bandwidth, index)


def describe(variant: Variant) -> str:
    size = f"{quality_height(variant)}p" if variant.resolution else "unknown size"
    return f"{size}, {variant.bandwidth // 1000} kbps"


def closest_to(entries: list[tuple[int, Variant]], target: int, notes: list[str]) -> Variant:
    """The best stream at or below ``target``; if all are larger, the smallest of them."""
    at_or_below = [entry for entry in entries if quality_height(entry[1]) <= target]
    if at_or_below:
        return max(at_or_below, key=best_key)[1]
    chosen = min(entries, key=worst_key)[1]
    notes.append(
        f"No stream is {target}p or smaller, so the closest one ({describe(chosen)}) was chosen."
    )
    return chosen
