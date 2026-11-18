"""Using a profile with command line options.

A command builds the engine's settings from every option it has, with defaults for the ones you
did not give. To lay *only the options you gave* over a profile, this module finds which options
were given (on the command line or in the environment, not from a default or a settings file)
and takes their values from the built settings.
"""

from __future__ import annotations

from typing import Any

import typer
from rayohx.config import DownloadConfig
from rayohx.platform.jobs import config_to_options

#: Option name (as the command's Python parameter) to the setting it sets: ``section.key``.
SETTING = {
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
    "audio_name": "selection.audio_names",
    "subtitles": "selection.subtitle_languages",
    "subtitle_name": "selection.subtitle_names",
    "video_only": "selection.video_only",
    "format_": "output.format",
    "overwrite": "output.overwrite",
    "validate": "output.validate",
    "remux_backend": "output.remux_backend",
    "ffmpeg": "output.ffmpeg_path",
    "name_template": "output.name_template",
    "verify": "verify.level",
    "checksum": "verify.expected_checksum",
    "metadata": "metadata.policy",
    "title": "metadata.title",
    "directory": "output.directory",
    "header": "network.headers",
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
    "credential_host": "network.credential_hosts",
    "concurrency": "concurrency",
    "resume": "resume",
    "allow_file_keys": "allow_file_keys",
    "storage": "storage.strategy",
    "workspace": "storage.workspace_dir",
    "buffer_size": "storage.buffer_bytes",
    "max_temp_size": "storage.max_temp_bytes",
    "space_check": "storage.check_space",
    "reserve_space": "storage.reserve_bytes",
    "keep_state": "storage.keep_state_on_failure",
}
#: Options that carry secrets. They are never part of a profile; they go with the job.
SECRET_ONLY = frozenset(
    {"cookie", "cookie_file", "proxy_username", "proxy_password", "client_key_password"}
)
_GIVEN = frozenset({"COMMANDLINE", "ENVIRONMENT"})


def given(ctx: typer.Context) -> set[str]:
    """The options the user gave, by Python parameter name."""
    found = set()
    for name in ctx.params:
        source = ctx.get_parameter_source(name)
        if source is not None and source.name in _GIVEN:
            found.add(name)
    return found


def overrides_from(
    ctx: typer.Context, config: DownloadConfig
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The settings the user gave (as option data) and the secrets they gave.

    ``config`` is the engine settings built from all the command's options.
    """
    options, secrets = config_to_options(config)
    chosen = given(ctx)
    overrides: dict[str, Any] = {}
    for name in sorted(chosen):
        path = SETTING.get(name)
        if path is None:
            continue
        section, _, key = path.partition(".")
        if not key:  # a top-level setting
            overrides[section] = options[section]
            continue
        overrides.setdefault(section, {})[key] = options[section][key]
    if not (chosen & SECRET_ONLY or chosen & {"header", "proxy", "cookie"}):
        secrets = {}
    return overrides, secrets


def with_profile(ctx: typer.Context, config: DownloadConfig, ref: str) -> DownloadConfig:
    """The settings of profile ``ref`` with the options the user gave laid over them."""
    from rayohx.errors import RayoHXError
    from rayohx.platform.profiles import check, to_config

    from rayohx_cli.cli.common import usage_error
    from rayohx_cli.cli.queue import open_platform

    overrides, secrets = overrides_from(ctx, config)
    rayo = open_platform()
    try:
        profile = rayo.profiles.require(ref)
        check(profile, machine_checks=True)
        return to_config(profile, overrides, secrets)
    except RayoHXError as exc:
        usage_error(exc)
    finally:
        rayo.close()
