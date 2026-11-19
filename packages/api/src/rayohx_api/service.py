"""The platform the API runs on: one ``Rayo`` per process, and what a client may queue.

Routes call this module; the work itself is done by ``rayohx.platform``. Jobs are stored in the
platform's database, so they survive a restart of the API.
"""

import logging
import threading
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from rayohx import Rayo
from rayohx.config import DownloadConfig, validate_url
from rayohx.downloader import Downloader
from rayohx.downloader.batch import batch_outputs
from rayohx.errors import ConfigurationError
from rayohx.platform import JobRecord, QueuePriority, RetryPolicy
from rayohx.platform.errors import RunnerLockedError
from rayohx.platform.jobs import NO_RETRY, config_to_options, safe_filename
from rayohx.platform.profiles import deep_merge

from rayohx_api.build import DEFAULT_CONCURRENCY, download_config, sources
from rayohx_api.config import Settings, get_settings
from rayohx_api.defaults import DefaultsStore, default_file, merge
from rayohx_api.migrate import import_v1_defaults
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
    store = DefaultsStore(settings.defaults_file or default_file())
    try:
        import_v1_defaults(rayo, store)  # once, and it keeps the old file
    except Exception:
        logger.warning("Importing the saved default options failed.", exc_info=True)
    return rayo, store


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


#: Request field to the setting it sets, for the options a request may lay over a profile.
_SETTING = {
    "selection": {
        "quality": "selection.quality",
        "max_resolution": "selection.max_resolution",
        "max_bitrate": "selection.max_bitrate",
        "variant": "selection.variant",
        "resolution": "selection.resolution",
        "bandwidth": "selection.bandwidth",
        "variant_name": "selection.variant_name",
        "codec": "selection.codec",
        "video_range": "selection.video_range",
        "max_frame_rate": "selection.max_frame_rate",
        "audio": "selection.audio_languages",
        "audio_names": "selection.audio_names",
        "subtitles": "selection.subtitle_languages",
        "subtitle_names": "selection.subtitle_names",
        "video_only": "selection.video_only",
    },
    "storage": {
        "strategy": "storage.strategy",
        "workspace": "storage.workspace_dir",
        "buffer_bytes": "storage.buffer_bytes",
        "max_temp_bytes": "storage.max_temp_bytes",
        "reserve_bytes": "storage.reserve_bytes",
        "space_check": "storage.check_space",
        "keep_state": "storage.keep_state_on_failure",
    },
    "output": {
        "format": "output.format",
        "directory": "output.directory",
        "overwrite": "output.overwrite",
        "validate_output": "output.validate",
        "remux_backend": "output.remux_backend",
        "ffmpeg": "output.ffmpeg_path",
    },
    "engine": {
        "concurrency": "concurrency",
        "resume": "resume",
        "allow_file_keys": "allow_file_keys",
    },
    "network": {
        "headers": "network.headers",
        "referer": "network.headers",
        "origin": "network.headers",
        "user_agent": "network.user_agent",
        "backoff": "network.backoff_factor",
        "max_redirects": "network.max_redirects",
        "insecure": "network.verify_tls",
        "ca_bundle": "network.verify_tls",
        "env_proxy": "network.proxy_from_env",
        "proxy": "network.proxy",
        "client_cert": "network.client_cert",
        "client_key": "network.client_key",
        "connect_timeout": "network.connect_timeout",
        "read_timeout": "network.read_timeout",
        "timeout": "network.total_timeout",
        "retries": "network.retries",
        "rate_limit": "network.rate_limit",
        "credential_hosts": "network.credential_hosts",
    },
}


def _given_overrides(
    request: DownloadCreate, config: DownloadConfig
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The settings the request itself set (not defaults), and its secrets."""
    options, secrets = config_to_options(config)
    overrides: dict[str, Any] = {}
    for section, names in _SETTING.items():
        given = getattr(request, section).model_fields_set
        for name in given & set(names):
            top, _, key = names[name].partition(".")
            if key:
                overrides.setdefault(top, {})[key] = options[top][key]
            else:
                overrides[top] = options[top]
    network = request.network.model_fields_set
    if not network & {"headers", "cookies", "cookie_file", "proxy", "client_key_password"}:
        secrets = {}
    return overrides, secrets


def enqueue(
    body: DownloadCreate,
    settings: Settings,
    *,
    priority: QueuePriority = QueuePriority.NORMAL,
    retry: RetryPolicy | None = NO_RETRY,
    profile: str | None = None,
    platform: bool = False,
    extra: Mapping[str, Any] | None = None,
) -> list[JobRecord]:
    """Queue one job for each address in the request.

    With a profile (named, or the default one), the profile's settings apply and only what the
    request set itself is laid over them. Without one, the saved default options are merged in.
    """
    chosen = rayo().profiles.require(profile) if profile else rayo().profiles.default()
    if chosen is not None or platform:
        return _enqueue_with_profile(
            body, settings, chosen.id if chosen else None, priority, retry, extra
        )
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


def _enqueue_with_profile(
    body: DownloadCreate,
    settings: Settings,
    profile_id: str | None,
    priority: QueuePriority,
    retry: RetryPolicy | None,
    extra: Mapping[str, Any] | None = None,
) -> list[JobRecord]:
    request = DownloadCreate.model_validate(body.model_dump(exclude_unset=True))
    urls = sources(request)
    if request.filename and len(urls) > 1:
        raise ConfigurationError("A file name can only be given for a single download.")
    filename = safe_filename(request.filename) if request.filename else None
    base = settings.download_dir
    config = download_config(
        request, base=base, local=settings.allow_local_paths, concurrency=DEFAULT_CONCURRENCY
    )
    overrides, secrets = _given_overrides(request, config)
    if extra:
        overrides = deep_merge(overrides, extra)
    for address in urls:
        validate_url(address)
    jobs = [
        rayo().queue.add(
            address,
            profile=profile_id,
            overrides=overrides,
            secrets=secrets,
            output_name=filename,
            playlist_text=request.playlist_text,
            priority=priority,
            retry=retry,
        )
        for address in urls
    ]
    ensure_runner()
    return jobs


def output_name(record: JobRecord) -> str | None:
    """The finished file's name only: clients never learn the server's folders."""
    return Path(record.output_path).name if record.output_path else None
