"""Finding the title, description, chapters and so on in a stream's playlists."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rayohx._redaction import redact_url
from rayohx.metadata.model import Chapter, MetadataInfo

if TYPE_CHECKING:
    from rayohx.models import AudioTrack, MasterPlaylist, MediaPlaylist, SessionData

#: ``EXT-X-SESSION-DATA`` ids that name each field, lower case. Apple's own ids come first.
_TITLE = ("com.apple.hls.title", "title", "com.apple.hls.name", "name")
_DESCRIPTION = ("com.apple.hls.description", "description", "synopsis", "summary")
_ARTWORK = ("com.apple.hls.artwork", "artwork", "poster", "thumbnail", "cover", "image")
_LANGUAGE = ("com.apple.hls.language", "language")
MAX_TEXT = 1000


def _clean(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = "".join(ch for ch in text if ch == "\n" or ord(ch) >= 32).strip()
    return cleaned[:MAX_TEXT] or None


def _find(items: tuple[SessionData, ...], ids: tuple[str, ...]) -> SessionData | None:
    by_id = {item.data_id.lower(): item for item in items}
    for wanted in ids:
        if wanted in by_id:
            return by_id[wanted]
    return None


def _web(url: str | None) -> str | None:
    return url if url and url.lower().startswith(("http://", "https://")) else None


def extract_metadata(
    master: MasterPlaylist | None,
    media: MediaPlaylist | None,
    *,
    url: str | None = None,
    audio: tuple[AudioTrack, ...] = (),
) -> MetadataInfo:
    """What the playlists say about the media.

    ``audio`` is the audio tracks that will be downloaded; the first one's language is used when
    the stream names none.
    """
    title = description = language = artwork = None
    if master is not None:
        data = master.session_data
        item = _find(data, _TITLE)
        title = _clean(item.value) if item else None
        item = _find(data, _DESCRIPTION)
        description = _clean(item.value) if item else None
        item = _find(data, _LANGUAGE)
        language = _clean(item.value) if item else None
        item = _find(data, _ARTWORK)
        artwork = _web(item.uri or item.value) if item else None
    if language is None and audio and audio[0].language:
        language = audio[0].language
    chapters: tuple[Chapter, ...] = ()
    duration = start = None
    if media is not None:
        duration = media.total_duration if media.is_vod and media.segments else None
        start = next((s.program_date_time for s in media.segments if s.program_date_time), None)
        chapters = _chapters(media, start)
    return MetadataInfo(
        title=title,
        description=description,
        language=language,
        duration=duration,
        artwork_url=artwork,
        chapters=chapters,
        start_time=start,
        source=redact_url(url) if url else None,
    )


def _chapters(media: MediaPlaylist, start: object) -> tuple[Chapter, ...]:
    """Chapters from date ranges that have a title, placed relative to the first segment."""
    if start is None or not media.date_ranges:
        return ()
    found: list[Chapter] = []
    for item in media.date_ranges:
        label = _clean(
            item.attributes.get("X-TITLE")
            or item.attributes.get("X-CHAPTER-TITLE")
            or item.attributes.get("TITLE")
        )
        if not label:
            continue
        begin = (item.start - start).total_seconds()  # type: ignore[operator]
        if begin < 0 or (media.is_vod and begin > media.total_duration):
            continue
        end = None
        if item.end is not None:
            end = (item.end - start).total_seconds()  # type: ignore[operator]
        elif item.duration is not None:
            end = begin + item.duration
        found.append(
            Chapter(start=round(begin, 3), end=round(end, 3) if end else None, title=label)
        )
    found.sort(key=lambda c: c.start)
    return tuple(found)
