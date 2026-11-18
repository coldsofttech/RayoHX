"""Downloading several streams, one after another."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rayohx._download._output._names import name_from_url
from rayohx.cancellation import CancellationToken
from rayohx.config import DownloadConfig
from rayohx.downloader.controller import Downloader
from rayohx.enums import DownloadState
from rayohx.errors import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from rayohx.events import DownloadEvent
    from rayohx.models import DownloadResult


@dataclass(frozen=True, slots=True)
class BatchItem:
    """How one address of a batch ended."""

    url: str
    #: Where the file was meant to go, before the right extension was added.
    output: Path
    #: The result. ``None`` only for an address that was never started.
    result: DownloadResult | None = None
    #: The error, if it failed.
    exception: Exception | None = None

    @property
    def success(self) -> bool:
        return self.result is not None and self.result.success

    @property
    def skipped(self) -> bool:
        """Whether it was never started because an earlier download failed or was cancelled."""
        return self.result is None and self.exception is None


def download_many(
    urls: Sequence[str],
    directory: Path | str | None = None,
    *,
    config: DownloadConfig | None = None,
    stop_on_error: bool = False,
    on_event: Callable[[DownloadEvent], None] | None = None,
    cancel: CancellationToken | None = None,
) -> list[BatchItem]:
    """Download each address in ``urls`` in turn, into ``directory``.

    Files are named after their addresses, and two addresses that would get the same name get
    ``-2``, ``-3`` and so on. ``config`` applies to every download, and ``config.output.path`` is
    ignored. One failure does not stop the others unless ``stop_on_error`` is set; cancelling
    (through ``cancel``) always stops the batch, and what was not started is reported as skipped.
    Nothing is raised for a failed download: look at each item.

    Raises:
        ConfigurationError: If there are no addresses or one is not a web address.
    """
    if not urls:
        raise ConfigurationError("There is nothing to download.", hint="Give at least one address.")
    base = config or DownloadConfig()
    folder = Path(directory) if directory is not None else base.output.directory
    token = cancel if cancel is not None else CancellationToken()
    items = [
        BatchItem(url=url, output=path)
        for url, path in zip(urls, batch_outputs(urls, folder), strict=True)
    ]
    # Check every address first, so a typo in the last one does not waste the first downloads.
    downloaders = [
        Downloader(
            item.url,
            output=item.output,
            config=dataclasses.replace(base, output=dataclasses.replace(base.output, path=None)),
            cancel=token,
        )
        for item in items
    ]
    finished: list[BatchItem] = []
    stopped = False
    for item, downloader in zip(items, downloaders, strict=True):
        if stopped or token.is_cancelled:
            finished.append(item)
            continue
        if on_event is not None:
            downloader.events.subscribe(on_event)
        result = downloader.run()
        finished.append(dataclasses.replace(item, result=result, exception=downloader.exception))
        if result.state is DownloadState.CANCELLED or (stop_on_error and not result.success):
            stopped = True
    return finished


def batch_outputs(urls: Sequence[str], directory: Path | str | None = None) -> list[Path]:
    """Where each address of a batch is saved, before the right extension is added.

    Names come from the addresses; repeats get ``-2``, ``-3`` and so on.
    """
    folder = Path(directory) if directory is not None else Path()
    return [folder / stem for stem in _stems(urls)]


def _stems(urls: Sequence[str]) -> list[str]:
    seen: dict[str, int] = {}
    stems = []
    for url in urls:
        stem = name_from_url(url)
        seen[stem] = seen.get(stem, 0) + 1
        stems.append(stem if seen[stem] == 1 else f"{stem}-{seen[stem]}")
    return stems
