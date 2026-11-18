"""Saving a ``DownloadConfig`` as plain data and rebuilding it.

A queued job outlives the program that created it, so its settings are stored as JSON. This
codec splits them in two:

* ``options``: everything that is safe to keep in the database, export and show.
* ``secrets``: cookies, secret headers, proxy and key passwords. They go to a ``SecretStore``.

Settings that cannot be stored (a ``key_fetcher`` function) are refused when the job is queued,
not when it runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from rayohx.config import (
    DownloadConfig,
    NetworkConfig,
    OutputConfig,
    ProxyConfig,
    SelectionConfig,
    StorageConfig,
)
from rayohx.enums import OutputFormat, RemuxBackend, StorageStrategy
from rayohx.errors import ConfigurationError
from rayohx.redaction import is_sensitive_name, redact_url

if TYPE_CHECKING:
    from collections.abc import Mapping

OPTIONS_VERSION = 1


def _path(value: Path | None) -> str | None:
    return str(value) if value is not None else None


def _opt_path(value: Any) -> Path | None:
    return Path(value) if value else None


def config_to_options(config: DownloadConfig) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split ``config`` into storable options and secrets."""
    if config.key_fetcher is not None:
        raise ConfigurationError(
            "A custom key_fetcher cannot be queued, because it cannot be saved.",
            hint="Run this download directly with Downloader instead of queueing it.",
        )
    net = config.network
    secrets: dict[str, Any] = {}
    plain_headers = {k: v for k, v in net.headers.items() if not is_sensitive_name(k)}
    secret_headers = {k: v for k, v in net.headers.items() if is_sensitive_name(k)}
    if secret_headers:
        secrets["headers"] = secret_headers
    if net.cookies:
        secrets["cookies"] = dict(net.cookies)
    if net.client_key_password:
        secrets["client_key_password"] = net.client_key_password
    proxy: dict[str, Any] | None = None
    if net.proxy is not None:
        proxy = {"url": net.proxy.url}
        if redact_url(net.proxy.url) != net.proxy.url:
            secrets["proxy_url"] = net.proxy.url
            proxy = {"url": redact_url(net.proxy.url)}
        if net.proxy.username is not None:
            secrets["proxy_username"] = net.proxy.username
            secrets["proxy_password"] = net.proxy.password
    verify = net.verify_tls
    options: dict[str, Any] = {
        "version": OPTIONS_VERSION,
        "concurrency": config.concurrency,
        "resume": config.resume,
        "allow_file_keys": config.allow_file_keys,
        "network": {
            "headers": plain_headers,
            "user_agent": net.user_agent,
            "connect_timeout": net.connect_timeout,
            "read_timeout": net.read_timeout,
            "total_timeout": net.total_timeout,
            "retries": net.retries,
            "backoff_factor": net.backoff_factor,
            "max_redirects": net.max_redirects,
            "verify_tls": str(verify) if isinstance(verify, Path) else verify,
            "proxy": proxy,
            "proxy_from_env": net.proxy_from_env,
            "client_cert": _path(net.client_cert),
            "client_key": _path(net.client_key),
            "rate_limit": net.rate_limit,
            "credential_hosts": list(net.credential_hosts),
        },
        "storage": {
            "strategy": config.storage.strategy.value,
            "workspace_dir": _path(config.storage.workspace_dir),
            "buffer_bytes": config.storage.buffer_bytes,
            "max_temp_bytes": config.storage.max_temp_bytes,
            "reserve_bytes": config.storage.reserve_bytes,
            "keep_state_on_failure": config.storage.keep_state_on_failure,
            "check_space": config.storage.check_space,
        },
        "output": {
            "directory": _path(config.output.directory),
            "format": config.output.format.value,
            "overwrite": config.output.overwrite,
            "validate": config.output.validate,
            "remux_backend": config.output.remux_backend.value,
            "ffmpeg_path": _path(config.output.ffmpeg_path),
        },
        "selection": {
            "quality": config.selection.quality,
            "max_resolution": config.selection.max_resolution,
            "max_bitrate": config.selection.max_bitrate,
            "audio_languages": list(config.selection.audio_languages),
            "subtitle_languages": list(config.selection.subtitle_languages),
            "audio_names": list(config.selection.audio_names),
            "subtitle_names": list(config.selection.subtitle_names),
            "video_only": config.selection.video_only,
            "variant": config.selection.variant,
            "resolution": config.selection.resolution,
            "bandwidth": config.selection.bandwidth,
            "variant_name": config.selection.variant_name,
            "codec": config.selection.codec,
            "video_range": config.selection.video_range,
            "max_frame_rate": config.selection.max_frame_rate,
        },
    }
    return options, secrets


def _pick(section: Mapping[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    """The named keys that are present and not ``None``, so dataclass defaults apply."""
    return {n: section[n] for n in names if section.get(n) is not None}


def config_from_options(
    options: Mapping[str, Any],
    secrets: Mapping[str, Any] | None = None,
    *,
    default_directory: Path | None = None,
) -> DownloadConfig:
    """Rebuild a ``DownloadConfig``. Raises ``ConfigurationError`` if the settings are not valid."""
    secret = secrets or {}
    try:
        return _build(options, secret, default_directory)
    except ConfigurationError:
        raise
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ConfigurationError(f"The saved download settings are not valid: {exc}") from exc


def _build(
    options: Mapping[str, Any], secret: Mapping[str, Any], default_directory: Path | None
) -> DownloadConfig:
    net = options.get("network") or {}
    storage = options.get("storage") or {}
    output = options.get("output") or {}
    selection = options.get("selection") or {}

    headers = {**(net.get("headers") or {}), **(secret.get("headers") or {})}
    network: dict[str, Any] = _pick(
        net,
        (
            "user_agent",
            "connect_timeout",
            "read_timeout",
            "total_timeout",
            "retries",
            "backoff_factor",
            "max_redirects",
            "proxy_from_env",
            "rate_limit",
        ),
    )
    network.update(
        headers=headers,
        cookies=dict(secret.get("cookies") or {}),
        credential_hosts=tuple(net.get("credential_hosts") or ()),
        client_cert=_opt_path(net.get("client_cert")),
        client_key=_opt_path(net.get("client_key")),
        client_key_password=secret.get("client_key_password"),
    )
    verify = net.get("verify_tls", True)
    network["verify_tls"] = Path(verify) if isinstance(verify, str) else bool(verify)
    proxy = net.get("proxy")
    if proxy:
        network["proxy"] = ProxyConfig(
            url=secret.get("proxy_url") or proxy["url"],
            username=secret.get("proxy_username"),
            password=secret.get("proxy_password"),
        )

    storage_kwargs = _pick(
        storage,
        ("buffer_bytes", "max_temp_bytes", "reserve_bytes", "keep_state_on_failure", "check_space"),
    )
    storage_kwargs["strategy"] = StorageStrategy(storage.get("strategy", "auto"))
    storage_kwargs["workspace_dir"] = _opt_path(storage.get("workspace_dir"))

    directory = _opt_path(output.get("directory")) or default_directory
    out_kwargs = _pick(output, ("overwrite", "validate"))
    out_kwargs.update(
        directory=directory,
        format=OutputFormat(output.get("format", "auto")),
        remux_backend=RemuxBackend(output.get("remux_backend", "auto")),
        ffmpeg_path=_opt_path(output.get("ffmpeg_path")),
    )

    sel_kwargs = _pick(
        selection,
        (
            "quality",
            "max_resolution",
            "max_bitrate",
            "video_only",
            "variant",
            "resolution",
            "bandwidth",
            "variant_name",
            "codec",
            "video_range",
            "max_frame_rate",
        ),
    )
    for name in ("audio_languages", "subtitle_languages", "audio_names", "subtitle_names"):
        sel_kwargs[name] = tuple(selection.get(name) or ())

    top = _pick(options, ("concurrency", "resume", "allow_file_keys"))
    return DownloadConfig(
        **top,
        network=NetworkConfig(**network),
        storage=StorageConfig(**storage_kwargs),
        output=OutputConfig(**out_kwargs),
        selection=SelectionConfig(**sel_kwargs),
    )
