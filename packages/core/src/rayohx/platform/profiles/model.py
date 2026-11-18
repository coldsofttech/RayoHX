"""Download profiles: named, reusable settings."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from rayohx.errors import ConfigurationError
from rayohx.platform.jobs.retry import RetryPolicy

if TYPE_CHECKING:
    from collections.abc import Mapping

SCHEMA_VERSION = 1
METADATA_POLICIES = ("preserve", "minimal", "none", "custom")
VERIFY_LEVELS = ("none", "basic", "strong")
MAX_NAME = 80
_SLUG = re.compile(r"[^a-z0-9]+")


def slug(name: str) -> str:
    """A stable, URL-safe id made from a name."""
    return _SLUG.sub("-", name.lower()).strip("-")[:40] or "profile"


def deep_merge(base: Mapping[str, Any], top: Mapping[str, Any]) -> dict[str, Any]:
    """``top`` laid over ``base``, section by section. Neither is changed."""
    merged = copy.deepcopy(dict(base))
    for key, value in top.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


@dataclass(frozen=True, slots=True, kw_only=True)
class DownloadProfile:
    """Everything a download needs that is not the address.

    ``options`` holds only the settings the profile *changes*, in the shape of
    ``rayohx.platform.jobs.config_to_options`` (sections ``selection``, ``output``, ``storage``,
    ``network``, and top-level ``concurrency`` and ``resume``). Everything else is the engine's
    default. A profile never holds secrets.

    ``metadata`` and ``verify`` are stored now and applied from the release that adds metadata
    handling and verification.
    """

    id: str
    name: str
    description: str = ""
    options: Mapping[str, Any] = field(default_factory=dict)
    retry: RetryPolicy | None = None
    #: A file name template (see ``rayohx.platform.profiles.naming``); ``None`` names the file
    #: after the address.
    naming: str | None = None
    metadata: str = "preserve"
    verify: str = "basic"
    builtin: bool = False
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", MappingProxyType(copy.deepcopy(dict(self.options))))
        if not self.name.strip():
            raise ConfigurationError("A profile needs a name.")
        if len(self.name) > MAX_NAME:
            raise ConfigurationError(f"A profile name can have at most {MAX_NAME} characters.")

    def to_dict(self) -> dict[str, Any]:
        """Plain data, as exported and as stored."""
        return {
            "name": self.name,
            "description": self.description,
            "options": copy.deepcopy(dict(self.options)),
            "retry": self.retry.to_dict() if self.retry else None,
            "naming": self.naming,
            "metadata": self.metadata,
            "verify": self.verify,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], *, profile_id: str, builtin: bool = False
    ) -> DownloadProfile:
        """Rebuild a profile from stored or imported data (after any needed migration)."""
        try:
            retry = data.get("retry")
            return cls(
                id=profile_id,
                name=str(data["name"]),
                description=str(data.get("description") or ""),
                options=dict(data.get("options") or {}),
                retry=RetryPolicy.from_dict(retry) if retry else None,
                naming=data.get("naming"),
                metadata=str(data.get("metadata", "preserve")),
                verify=str(data.get("verify", "basic")),
                builtin=builtin,
                schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError(f"The profile data is not valid: {exc}") from exc

    def changed(self, **changes: Any) -> DownloadProfile:
        import dataclasses

        return dataclasses.replace(self, **changes)
