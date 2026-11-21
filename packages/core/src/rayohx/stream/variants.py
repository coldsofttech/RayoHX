"""Choosing the video variant."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    from rayohx.stream._ranking import best_key, closest_to, describe, is_audio_only, worst_key
    from rayohx.stream.quality import quality_height

    notes = notes if notes is not None else []
    if not variants:
        from rayohx.errors import PlaylistError

        raise PlaylistError("The playlist lists no streams to download.")

    entries = list(enumerate(variants))
    if config.variant is not None:
        if config.variant > len(entries):
            from rayohx.errors import ConfigurationError

            raise ConfigurationError(
                f"There is no stream number {config.variant}.",
                hint=f"The playlist lists {len(entries)} stream(s), numbered from 1.",
            )
        return entries[config.variant - 1][1]
    entries = _exact_matches(entries, config, notes)
    video = [entry for entry in entries if not is_audio_only(entry[1])]
    entries = video or entries
    entries = _preferred(entries, config, notes)

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
        and (
            config.max_frame_rate is None
            or not entry[1].frame_rate
            or entry[1].frame_rate <= config.max_frame_rate
        )
    ]
    if not allowed:
        chosen = min(entries, key=worst_key)[1]
        notes.append(
            "No stream fits the resolution, bitrate or frame rate limit, so the smallest one "
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


def _preferred(
    entries: list[tuple[int, Variant]], config: SelectionConfig, notes: list[str]
) -> list[tuple[int, Variant]]:
    """Keep the streams with the preferred codec and dynamic range, if any have them."""
    from rayohx.config.selection import CODEC_FAMILIES

    if config.codec is not None:
        prefixes = CODEC_FAMILIES[config.codec]
        matching = [e for e in entries if any(c.lower().startswith(prefixes) for c in e[1].codecs)]
        if matching:
            entries = matching
        else:
            notes.append(f"No stream uses {config.codec}, so the other codecs were considered.")
    if config.video_range is not None:
        wanted = config.video_range
        matching = [e for e in entries if _range_matches(e[1].video_range, wanted)]
        if matching:
            entries = matching
        else:
            notes.append(
                f"No stream has {wanted.upper()} video, so the other dynamic ranges were "
                "considered."
            )
    return entries


def _range_matches(video_range: str | None, wanted: str) -> bool:
    actual = (video_range or "sdr").lower()
    return actual in ("pq", "hlg") if wanted == "hdr" else actual == wanted


def _exact_matches(
    entries: list[tuple[int, Variant]], config: SelectionConfig, notes: list[str]
) -> list[tuple[int, Variant]]:
    """Keep the streams that match the exact size, bandwidth and name that were asked for."""
    found = entries
    wanted: list[str] = []
    if config.resolution is not None:
        wanted.append(f"size {config.resolution}")
        found = [e for e in found if e[1].resolution and str(e[1].resolution) == config.resolution]
    if config.bandwidth is not None:
        wanted.append(f"bandwidth {config.bandwidth}")
        found = [e for e in found if config.bandwidth in (e[1].bandwidth, e[1].average_bandwidth)]
    if config.variant_name is not None:
        wanted.append(f"name {config.variant_name!r}")
        name = config.variant_name.strip().lower()
        found = [e for e in found if (e[1].name or "").strip().lower() == name]
    if not wanted:
        return entries
    if not found:
        from rayohx.errors import ConfigurationError
        from rayohx.stream._ranking import describe_full

        listing = "; ".join(f"{index + 1}: {describe_full(v)}" for index, v in entries)
        raise ConfigurationError(
            f"No stream has {' and '.join(wanted)}.", hint=f"The streams are {listing}."
        )
    if len(found) > 1:
        notes.append(f"{len(found)} streams have {' and '.join(wanted)}; the best of them is used.")
    return found
