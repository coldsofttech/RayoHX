"""Checking a profile before it is saved or used.

A profile is checked in two ways:

* **Structure** (always): known settings, valid values, no secrets, a usable naming template. A
  profile that fails this cannot be saved.
* **This machine** (when capabilities are given): can the output format it asks for be made here?
  A profile may be saved or imported for another machine, so this is only checked when a job is
  queued from it.

Problems come back as ``Finding`` objects, so a front end can show all of them at once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from rayohx.capabilities import Capabilities, detect, output_requirements
from rayohx.config import DownloadConfig
from rayohx.enums import OutputFormat, RemuxBackend
from rayohx.errors import ConfigurationError
from rayohx.platform.jobs.options import config_from_options, config_to_options
from rayohx.platform.profiles.model import (
    METADATA_POLICIES,
    SCHEMA_VERSION,
    VERIFY_LEVELS,
    DownloadProfile,
    deep_merge,
)
from rayohx.platform.profiles.naming import validate_template
from rayohx.redaction import is_sensitive_name, redact_url

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


#: Network settings that only ever hold secrets; they are stored apart from options.
SECRET_SETTINGS = frozenset({"cookies", "client_key_password", "proxy_username", "proxy_password"})


@dataclass(frozen=True, slots=True)
class Finding:
    """One problem found in a profile."""

    level: str  # "error" or "warning"
    field: str
    message: str
    hint: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "level": self.level,
            "field": self.field,
            "message": self.message,
            "hint": self.hint,
        }

    def __str__(self) -> str:
        text = f"{self.field}: {self.message}"
        return f"{text} {self.hint}" if self.hint else text


def default_options() -> dict[str, Any]:
    """Every setting at the engine's default. The shape profile options are laid over."""
    options, _ = config_to_options(DownloadConfig())
    return options


def known_settings() -> dict[str, set[str] | None]:
    """Section name to the settings in it (``None`` for a top-level setting)."""
    known: dict[str, set[str] | None] = {}
    for key, value in default_options().items():
        if key == "version":
            continue
        known[key] = set(value) if isinstance(value, dict) else None
    return known


def structure(profile: DownloadProfile) -> list[Finding]:
    """Problems that make a profile unusable anywhere."""
    found: list[Finding] = []
    if profile.schema_version > SCHEMA_VERSION:
        found.append(
            Finding(
                "error",
                "schema_version",
                "The profile was made by a newer RayoHX.",
                "Update RayoHX.",
            )
        )
    known = known_settings()
    for key, value in profile.options.items():
        if key == "version":
            continue
        if key not in known:
            found.append(Finding("error", key, f"{key!r} is not a setting.", _suggest(key, known)))
        elif known[key] is None:
            continue
        elif not isinstance(value, dict):
            found.append(Finding("error", key, f"{key!r} must hold named settings."))
        else:
            for inner in value:
                if key == "network" and inner in SECRET_SETTINGS:
                    continue  # reported as a secret below
                if inner not in (known[key] or set()):
                    found.append(
                        Finding("error", f"{key}.{inner}", f"{key}.{inner} is not a setting.")
                    )
    found += _secrets(profile.options)
    merged = deep_merge(default_options(), profile.options)
    if not any(f.level == "error" for f in found):
        try:
            config_from_options(merged, {})
        except ConfigurationError as exc:
            found.append(Finding("error", "options", exc.message, exc.hint))
    if profile.naming is not None:
        try:
            validate_template(profile.naming)
        except ConfigurationError as exc:
            found.append(Finding("error", "naming", exc.message, exc.hint))
    if profile.metadata not in METADATA_POLICIES:
        found.append(
            Finding(
                "error",
                "metadata",
                f"{profile.metadata!r} is not a metadata policy.",
                f"Use one of: {', '.join(METADATA_POLICIES)}.",
            )
        )
    if profile.verify not in VERIFY_LEVELS:
        found.append(
            Finding(
                "error",
                "verify",
                f"{profile.verify!r} is not a verification level.",
                f"Use one of: {', '.join(VERIFY_LEVELS)}.",
            )
        )
    return found


def _suggest(key: str, known: Mapping[str, object]) -> str:
    return f"Settings are: {', '.join(sorted(known))}."


def _secrets(options: Mapping[str, Any]) -> list[Finding]:
    """Profiles are shared and exported, so they never hold cookies, passwords or tokens."""
    found: list[Finding] = []
    network = options.get("network") or {}
    if not isinstance(network, dict):
        return found
    hint = "Give secrets when you add the download, not in a profile."
    for name in network.get("headers") or {}:
        if is_sensitive_name(str(name)):
            found.append(
                Finding("error", f"network.headers.{name}", "A profile cannot hold secrets.", hint)
            )
    for key in sorted(SECRET_SETTINGS):
        if network.get(key):
            found.append(Finding("error", f"network.{key}", "A profile cannot hold secrets.", hint))
    proxy = network.get("proxy")
    if (
        isinstance(proxy, dict)
        and proxy.get("url")
        and redact_url(str(proxy["url"])) != proxy["url"]
    ):
        found.append(
            Finding("error", "network.proxy.url", "The proxy address holds a login.", hint)
        )
    return found


def machine(profile: DownloadProfile, capabilities: Capabilities | None = None) -> list[Finding]:
    """Problems that stop the profile working on this machine."""
    merged = deep_merge(default_options(), profile.options)
    output = merged.get("output", {})
    try:
        fmt = OutputFormat(output.get("format", "auto"))
        backend = RemuxBackend(output.get("remux_backend", "auto"))
    except ValueError:
        return []  # reported by structure()
    needs = output_requirements(fmt)
    if not needs:
        return []
    found: list[Finding] = []
    if backend is RemuxBackend.NATIVE:
        found.append(
            Finding(
                "error",
                "output.remux_backend",
                f"{fmt.value} output needs FFmpeg, but only the built-in remuxer is allowed.",
                "Set the remux backend to auto or ffmpeg.",
            )
        )
    caps = capabilities if capabilities is not None else detect(output.get("ffmpeg_path"))
    if not caps.supports(fmt):
        found.append(
            Finding(
                "error",
                "output.format",
                f"{fmt.value} output needs FFmpeg, which was not found.",
                "Install FFmpeg, set its path in the output settings, or choose another format.",
            )
        )
    return found


def validate(
    profile: DownloadProfile,
    capabilities: Capabilities | None = None,
    *,
    machine_checks: bool = False,
) -> list[Finding]:
    """All problems with ``profile``. ``machine_checks`` adds what this machine cannot do."""
    found = structure(profile)
    if machine_checks and not any(f.level == "error" for f in found):
        found += machine(profile, capabilities)
    return found


def check(
    profile: DownloadProfile,
    capabilities: Capabilities | None = None,
    *,
    machine_checks: bool = False,
) -> None:
    """Raise ``ConfigurationError`` listing every error in ``profile``."""
    errors = [
        f
        for f in validate(profile, capabilities, machine_checks=machine_checks)
        if f.level == "error"
    ]
    if not errors:
        return
    first = errors[0]
    more = f" (and {len(errors) - 1} more)" if len(errors) > 1 else ""
    raise ConfigurationError(
        f"The profile {profile.name!r} is not valid: {first.field}: {first.message}{more}",
        hint=first.hint,
    )


def resolve_options(
    profile: DownloadProfile | None, overrides: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """The full settings: the defaults, then the profile's, then the caller's."""
    merged = default_options()
    if profile is not None:
        merged = deep_merge(merged, profile.options)
    if overrides:
        merged = deep_merge(merged, overrides)
    return merged


def to_config(
    profile: DownloadProfile | None,
    overrides: Mapping[str, Any] | None = None,
    secrets: Mapping[str, Any] | None = None,
    *,
    default_directory: Path | None = None,
) -> DownloadConfig:
    """The engine settings a profile (and overrides, and secrets) describe."""
    return config_from_options(
        resolve_options(profile, overrides), secrets or {}, default_directory=default_directory
    )
