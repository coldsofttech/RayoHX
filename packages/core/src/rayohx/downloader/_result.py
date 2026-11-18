"""Building the result of a download."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rayohx.enums import Processing
from rayohx.models import OutputInfo

if TYPE_CHECKING:
    from pathlib import Path

    from rayohx._download._media import DownloadSummary
    from rayohx.enums import ContainerFormat


def join_message(message: str, hint: str | None) -> str:
    return f"{message} {hint}" if hint else message


def output_info(
    path: Path,
    summary: DownloadSummary,
    container: ContainerFormat,
    processing: Processing = Processing.COPIED,
) -> OutputInfo:
    final = summary.output or path
    if final.is_dir():
        size = sum(item.stat().st_size for item in final.iterdir() if item.is_file())
    else:
        size = final.stat().st_size
    return OutputInfo(path=final, container=container, size_bytes=size, processing=processing)
