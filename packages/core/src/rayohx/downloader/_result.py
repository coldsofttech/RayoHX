"""Building the result of a download."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from rayohx._download._media import DownloadSummary
    from rayohx.enums import ContainerFormat
    from rayohx.models import OutputInfo


def join_message(message: str, hint: str | None) -> str:
    return f"{message} {hint}" if hint else message


def output_info(path: Path, summary: DownloadSummary, container: ContainerFormat) -> OutputInfo:
    from rayohx.models import OutputInfo

    final = summary.output or path
    if final.is_dir():
        size = sum(item.stat().st_size for item in final.iterdir() if item.is_file())
    else:
        size = final.stat().st_size
    return OutputInfo(path=final, container=container, size_bytes=size)
