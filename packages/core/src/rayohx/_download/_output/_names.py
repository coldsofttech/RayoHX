"""Safe file names, from text, from web addresses, and for separate segment files."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from rayohx.enums import ContainerFormat

_SEGMENT_SUFFIX = {ContainerFormat.MPEG_TS: ".ts", ContainerFormat.FMP4: ".m4s"}
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
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
MAX_NAME_LENGTH = 80


def sanitize_filename(text: str, default: str = "video") -> str:
    """Turn arbitrary text (such as part of a web address) into a safe file name stem.

    The result has only letters, digits, dots, dashes and underscores, never starts with a dot, is
    never a reserved Windows device name, and cannot contain a path separator.
    """
    cleaned = _UNSAFE.sub("_", text).strip("._-")
    cleaned = re.sub(r"_+", "_", cleaned)[:MAX_NAME_LENGTH].strip("._-")
    if not cleaned:
        return default
    if cleaned.split(".")[0].lower() in _RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned


def name_from_url(url: str) -> str:
    """A file name stem taken from the last part of a web address."""
    generic = {"index", "master", "playlist", "main", "manifest"}
    for part in reversed([p for p in unquote(urlsplit(url).path).split("/") if p]):
        stem = Path(part).stem
        if stem.lower() not in generic:
            return sanitize_filename(stem)
    return "video"


def segment_file_name(index: int, container: ContainerFormat, *, init: bool = False) -> str:
    """The name of a separate segment file, for example ``segment-00001.ts``."""
    if init:
        return f"init-{index:05d}.mp4"
    return f"segment-{index + 1:05d}{_SEGMENT_SUFFIX.get(container, '.bin')}"
