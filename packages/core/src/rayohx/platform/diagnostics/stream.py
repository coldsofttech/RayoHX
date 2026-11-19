"""Looking at a stream and saying what is unusual about it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from rayohx.errors import RayoHXError
from rayohx.media import MediaInfo, inspect_media
from rayohx.platform.diagnostics.explain import explain

if TYPE_CHECKING:
    from pathlib import Path

    from rayohx.config import NetworkConfig, SelectionConfig


@dataclass(frozen=True, slots=True)
class Finding:
    """Something worth knowing about what was examined."""

    level: str  # "error", "warning" or "info"
    title: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"level": self.level, "title": self.title, "detail": self.detail}


@dataclass(frozen=True, slots=True, kw_only=True)
class StreamReport:
    """A stream described, with what is unusual about it."""

    media: dict[str, Any] | None
    findings: tuple[Finding, ...]
    #: The error code when the stream could not be read at all.
    code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "media": self.media,
            "code": self.code,
            "findings": [f.to_dict() for f in self.findings],
        }


def findings_for(info: MediaInfo) -> list[Finding]:
    """What is notable in a stream's description."""
    found: list[Finding] = []
    add = found.append
    if info.live:
        add(Finding("error", "A live stream", "It has no end; live streams cannot be downloaded."))
    if info.encryption == "SAMPLE-AES":
        add(Finding("error", "SAMPLE-AES encryption", "This kind of protection is not supported."))
    elif info.encryption:
        add(Finding("info", f"Encrypted with {info.encryption}", "Decrypted while downloading."))
    if info.discontinuities:
        add(
            Finding(
                "warning",
                f"{info.discontinuities} break(s) in the stream",
                "Where it breaks (often at advertisements) the picture or sound may glitch "
                "or the timing may jump.",
            )
        )
    if info.container is None:
        add(
            Finding(
                "warning",
                "The segment format is not known",
                "Only MPEG-TS and fragmented MP4 work.",
            )
        )
    if info.video is None and not info.audio:
        add(Finding("warning", "No streams were found", "The playlist lists nothing to download."))
    elif info.video is None:
        add(Finding("info", "Audio only", "There is no video in this stream."))
    if info.video is not None and info.video.codec is None:
        add(Finding("info", "The video codec is not stated", "Install ffprobe to look inside."))
    if info.size.kind == "unavailable" and not info.live:
        add(Finding("info", "The size cannot be told", info.size.basis))
    if info.size.kind == "estimated":
        add(Finding("info", "The size is an estimate", info.size.basis))
    for note in info.notes:
        add(Finding("info", note))
    return found


def diagnose_stream(
    url: str,
    *,
    network: NetworkConfig | None = None,
    selection: SelectionConfig | None = None,
    playlist_text: str | None = None,
    probe: bool = True,
    ffprobe: Path | str | None = None,
) -> StreamReport:
    """Describe a stream and list what is unusual. Failing to read it is a finding, not a crash."""
    try:
        info = inspect_media(
            url,
            network=network,
            selection=selection,
            playlist_text=playlist_text,
            probe=probe,
            ffprobe=ffprobe,
        )
    except RayoHXError as exc:
        why = explain(exc.code)
        return StreamReport(
            media=None, findings=(Finding("error", why.title, exc.describe()),), code=exc.code
        )
    return StreamReport(media=info.to_dict(), findings=tuple(findings_for(info)))
