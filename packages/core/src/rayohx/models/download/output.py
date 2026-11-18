"""The file a download produced."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rayohx.enums import Processing

if TYPE_CHECKING:
    from pathlib import Path

    from rayohx.enums import ContainerFormat


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputInfo:
    """The file a download produced."""

    path: Path
    container: ContainerFormat
    size_bytes: int
    #: What was done to the data on its way to this file.
    processing: Processing = Processing.COPIED
