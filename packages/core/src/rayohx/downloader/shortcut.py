"""The ``download()`` function: the whole job in one call."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from rayohx.cancellation import CancellationToken
    from rayohx.config import DownloadConfig
    from rayohx.enums import OutputFormat
    from rayohx.events import DownloadEvent
    from rayohx.models import DownloadResult

T = TypeVar("T")


def download(
    url: str,
    output: Path | str | None = None,
    *,
    config: DownloadConfig | None = None,
    quality: str | None = None,
    max_resolution: str | None = None,
    max_bitrate: int | None = None,
    audio: str | Sequence[str] | None = None,
    subtitles: str | Sequence[str] | None = None,
    video_only: bool | None = None,
    format: OutputFormat | str | None = None,
    overwrite: bool | None = None,
    concurrency: int | None = None,
    resume: bool | None = None,
    on_event: Callable[[DownloadEvent], None] | None = None,
    cancel: CancellationToken | None = None,
) -> DownloadResult:
    """Download the stream at ``url`` to ``output``.

    ``output`` may be a file name, or ``None`` to name the file after the address in the current
    folder. The keyword options override ``config``; use ``config`` for everything else, such as
    headers, cookies, a proxy or the storage strategy.

    Returns a ``DownloadResult``, which is also what a cancelled download returns (check
    ``result.cancelled``).

    Raises:
        RayoHXError: If the download fails; the message says what went wrong and what to try.
    """
    from rayohx.config import DownloadConfig
    from rayohx.downloader.controller import Downloader
    from rayohx.enums import DownloadState, OutputFormat

    base = config or DownloadConfig()
    selection = replace(
        base.selection,
        quality=quality,
        max_resolution=max_resolution,
        max_bitrate=max_bitrate,
        audio_languages=languages(audio),
        subtitle_languages=languages(subtitles),
        video_only=video_only,
    )
    output_config = replace(
        base.output,
        format=OutputFormat(format) if format is not None else None,
        overwrite=overwrite,
    )
    merged = replace(
        base,
        selection=selection,
        output=output_config,
        concurrency=concurrency,
        resume=resume,
    )
    downloader = Downloader(url, output=output, config=merged, cancel=cancel)
    if on_event is not None:
        downloader.events.subscribe(on_event)
    result = downloader.run()
    if result.state is DownloadState.FAILED and downloader.exception is not None:
        raise downloader.exception
    return result


def languages(value: str | Sequence[str] | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    return (value,) if isinstance(value, str) else tuple(value)


def replace(instance: T, **changes: object) -> T:
    """``dataclasses.replace`` that skips options that were not given."""
    import dataclasses

    given = {name: value for name, value in changes.items() if value is not None}
    return dataclasses.replace(instance, **given) if given else instance  # type: ignore[type-var]
