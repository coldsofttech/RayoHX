"""The platform the API runs on: one ``Rayo`` per process, and what a client may queue.

Routes call this module; the work itself is done by ``rayohx.platform``. Jobs are stored in the
platform's database, so they survive a restart of the API.
"""

import logging
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

from rayohx import Rayo
from rayohx.config import validate_url
from rayohx.downloader import Downloader
from rayohx.downloader.batch import batch_outputs
from rayohx.errors import ConfigurationError
from rayohx.platform import JobRecord, QueuePriority, RetryPolicy
from rayohx.platform.errors import RunnerLockedError
from rayohx.platform.jobs import NO_RETRY, safe_filename

from rayohx_api.build import DEFAULT_CONCURRENCY, download_config, sources
from rayohx_api.config import Settings, get_settings
from rayohx_api.defaults import DefaultsStore, default_file, merge
from rayohx_api.schemas_v1 import DownloadCreate

logger = logging.getLogger(__name__)
_start_lock = threading.Lock()


def _downloader(*args: Any, **kwargs: Any) -> Downloader:
    # Looked up at call time, so tests can replace ``Downloader`` in this module.
    return Downloader(*args, **kwargs)


@lru_cache
def _state() -> tuple[Rayo, DefaultsStore]:
    settings = get_settings()
    rayo = Rayo(
        home=settings.home,
        download_dir=settings.download_dir,
        max_active=settings.max_active_downloads,
        downloader_factory=_downloader,
    )
    return rayo, DefaultsStore(settings.defaults_file or default_file())


def reset_state() -> None:
    """Stop the queue and forget the platform (tests pair this with ``cache_clear``)."""
    if _state.cache_info().currsize:
        _state()[0].close()
    _state.cache_clear()


def rayo() -> Rayo:
    return _state()[0]


def store() -> DefaultsStore:
    return _state()[1]


def ensure_runner() -> None:
    """Run queued jobs in this process, unless another process already does."""
    queue = rayo().queue
    with _start_lock:
        if queue.running:
            return
        try:
            queue.start()
        except RunnerLockedError:
            logger.info("Another process runs the queue; this one only controls it.")


def enqueue(
    body: DownloadCreate,
    settings: Settings,
    *,
    priority: QueuePriority = QueuePriority.NORMAL,
    retry: RetryPolicy = NO_RETRY,
) -> list[JobRecord]:
    """Queue one job for each address in the request, after merging the saved defaults."""
    merged = merge(store().get(), body.model_dump(exclude_unset=True))
    request = DownloadCreate.model_validate(merged)
    urls = sources(request)
    if request.filename and len(urls) > 1:
        raise ConfigurationError("A file name can only be given for a single download.")
    filename = safe_filename(request.filename) if request.filename else None
    base = settings.download_dir
    config = download_config(
        request, base=base, local=settings.allow_local_paths, concurrency=DEFAULT_CONCURRENCY
    )
    folder = config.output.directory or base
    folder.mkdir(parents=True, exist_ok=True)
    names: list[str | None]
    if filename:
        names = [filename]
    elif len(urls) > 1:
        names = [path.name for path in batch_outputs(urls, folder)]
    else:
        names = [None]
    for address in urls:  # check every address first, so a typo in the last one queues nothing
        validate_url(address)
    jobs = [
        rayo().queue.add(
            address,
            config=config,
            output_name=name,
            playlist_text=request.playlist_text,
            priority=priority,
            retry=retry,
        )
        for address, name in zip(urls, names, strict=True)
    ]
    ensure_runner()
    return jobs


def output_name(record: JobRecord) -> str | None:
    """The finished file's name only: clients never learn the server's folders."""
    return Path(record.output_path).name if record.output_path else None
