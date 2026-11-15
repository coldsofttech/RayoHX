"""Checks and helpers shared by the settings modules."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING

from rayohx.errors import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Mapping


def frozen_map(value: Mapping[str, str]) -> Mapping[str, str]:
    """A read-only copy of ``value``."""
    return MappingProxyType(dict(value))


def check_positive(name: str, value: float | None, *, allow_none: bool = False) -> None:
    """Raise unless ``value`` is greater than zero (or ``None`` when that is allowed)."""
    if value is None:
        if not allow_none:
            raise ConfigurationError(f"{name} is required.")
        return
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero.")
