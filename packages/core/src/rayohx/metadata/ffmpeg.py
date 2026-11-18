"""Putting metadata into a file made by FFmpeg.

FFmpeg is only given values to store. Text is passed as separate arguments (never through a
shell), chapters go in a small file, and a cover picture is attached from a file that was checked
to really be a JPEG or PNG image.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from rayohx.metadata.model import MetadataInfo

if TYPE_CHECKING:
    from rayohx._http import HttpClient

logger = logging.getLogger(__name__)

MAX_ARTWORK_BYTES = 8 * 1024 * 1024
_JPEG, _PNG = b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True, slots=True)
class Support:
    """What kinds of metadata a kind of output file can hold."""

    tags: bool = False
    chapters: bool = False
    artwork: bool = False


#: By output file extension. Others (``.ts``, ``.aac``, ``.ac3``) hold none.
_SUPPORT = {
    ".mkv": Support(True, True, True),
    ".mka": Support(True, True, True),
    ".mp4": Support(True, True, True),
    ".m4a": Support(True, True, True),
    ".mp3": Support(True, False, True),
}


def support_for(path: Path) -> Support:
    return _SUPPORT.get(path.suffix.lower(), Support())


@dataclass(slots=True)
class FfmpegMetadata:
    """The metadata arguments for one FFmpeg run, and the temporary files they refer to."""

    tags: dict[str, str] = field(default_factory=dict)
    chapters_file: Path | None = None
    artwork: Path | None = None
    language: str | None = None
    #: What ended up in the file, by name, for the result.
    written: list[str] = field(default_factory=list)
    #: Why something was left out.
    notes: list[str] = field(default_factory=list)

    @property
    def mime(self) -> str:
        return "image/png" if self.artwork and self.artwork.suffix == ".png" else "image/jpeg"

    def cleanup(self) -> None:
        for path in (self.chapters_file, self.artwork):
            if path is not None:
                path.unlink(missing_ok=True)


def escape(value: str) -> str:
    """Escape a value for an FFmpeg metadata file."""
    out = value.replace("\\", "\\\\")
    for char in ("=", ";", "#"):
        out = out.replace(char, "\\" + char)
    return out.replace("\n", "\\\n")


def chapters_text(info: MetadataInfo, total: float | None) -> str:
    """The chapters as an FFmpeg metadata file."""
    lines = [";FFMETADATA1"]
    chapters = list(info.chapters)
    for position, chapter in enumerate(chapters):
        end = chapter.end
        if end is None or end <= chapter.start:
            following = chapters[position + 1].start if position + 1 < len(chapters) else total
            end = following if following and following > chapter.start else chapter.start + 1
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={round(chapter.start * 1000)}",
            f"END={round(end * 1000)}",
            f"title={escape(chapter.title)}",
        ]
    return "\n".join(lines) + "\n"


def tags_for(info: MetadataInfo) -> dict[str, str]:
    """The global tags to write."""
    tags: dict[str, str] = {}
    if info.title:
        tags["title"] = info.title
    if info.description:
        tags["description"] = info.description
        tags["comment"] = info.description
    if info.start_time:
        tags["creation_time"] = info.start_time.isoformat()
    return tags


def fetch_artwork(client: HttpClient, url: str, output: Path) -> Path | None:
    """Download a cover picture next to ``output``; the file is ``.jpg`` or ``.png`` by what it is.

    Returns ``None`` if the picture could not be fetched or is not really a JPEG or PNG.
    """
    try:
        data = client.fetch_bytes(url, max_bytes=MAX_ARTWORK_BYTES).content
    except Exception as exc:
        logger.info("The cover picture could not be fetched: %s", exc)
        return None
    if data.startswith(_JPEG):
        suffix = ".jpg"
    elif data.startswith(_PNG):
        suffix = ".png"
    else:
        return None
    target = output.with_name(f".{output.name}.cover{suffix}")
    target.write_bytes(data)
    return target


def prepare(
    info: MetadataInfo,
    output: Path,
    *,
    client: HttpClient | None,
    total_duration: float | None,
) -> FfmpegMetadata:
    """Work out what can go into ``output`` and write the helper files FFmpeg needs."""
    result = FfmpegMetadata()
    if info.empty and not info.description:
        return result
    support = support_for(output)
    if not (support.tags or support.chapters or support.artwork):
        result.notes.append(
            f"{output.suffix or 'This kind of file'} cannot hold metadata, so none was written."
        )
        return result
    if support.tags:
        result.tags = tags_for(info)
        result.written += [k for k in ("title", "description", "creation_time") if k in result.tags]
    if info.chapters:
        if support.chapters:
            path = output.with_name(f".{output.name}.chapters.txt")
            path.write_text(chapters_text(info, total_duration), encoding="utf-8")
            result.chapters_file = path
            result.written.append("chapters")
        else:
            result.notes.append("This kind of file cannot hold chapters.")
    if info.artwork_url:
        if support.artwork and client is not None:
            cover = fetch_artwork(client, info.artwork_url, output)
            if cover is not None:
                result.artwork = cover
                result.written.append("artwork")
            else:
                result.notes.append("The cover picture could not be used.")
        elif not support.artwork:
            result.notes.append("This kind of file cannot hold a cover picture.")
    if info.language and support.tags:
        result.language = info.language
        result.written.append("language")
    return result
