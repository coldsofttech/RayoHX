"""Checks and helpers shared by the settings modules."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


def frozen_map(value: Mapping[str, str]) -> Mapping[str, str]:
    """A read-only copy of ``value``."""
    from types import MappingProxyType

    return MappingProxyType(dict(value))


def check_positive(name: str, value: float | None, *, allow_none: bool = False) -> None:
    """Raise unless ``value`` is greater than zero (or ``None`` when that is allowed)."""
    if value is None:
        if not allow_none:
            from rayohx.errors import ConfigurationError

            raise ConfigurationError(f"{name} is required.")
        return
    if value <= 0:
        from rayohx.errors import ConfigurationError

        raise ConfigurationError(f"{name} must be greater than zero.")
