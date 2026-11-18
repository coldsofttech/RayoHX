"""Verification settings: how a finished download is checked."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rayohx.enums import VerifyLevel
from rayohx.errors import ConfigurationError

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

#: Checksum algorithms and the length of their hexadecimal form.
CHECKSUM_ALGORITHMS = {"md5": 32, "sha1": 40, "sha256": 64, "sha512": 128}
_HEX = re.compile(r"^[0-9a-fA-F]+$")


def infer_algorithm(expected: str) -> str | None:
    """The algorithm whose hexadecimal digests are as long as ``expected``."""
    for name, length in CHECKSUM_ALGORITHMS.items():
        if len(expected) == length and name != "sha1":
            return name
    return "sha1" if len(expected) == CHECKSUM_ALGORITHMS["sha1"] else None


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifyConfig:
    """How a finished download is checked.

    Nothing extra is done, and no checksum is calculated, unless asked for here.
    """

    level: VerifyLevel = VerifyLevel.NONE
    #: Calculate this checksum of the finished file (``md5``, ``sha1``, ``sha256``, ``sha512``).
    checksum: str | None = None
    #: The checksum the file must have. The algorithm is taken from its length if ``checksum``
    #: is not set. A different checksum fails the download.
    expected_checksum: str | None = None
    #: Keep a file that failed verification (renamed with ``.invalid``) instead of deleting it.
    keep_invalid: bool = True
    #: The ffprobe program to use for ``strong`` verification; found on the PATH if unset.
    ffprobe_path: Path | None = None

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "level", VerifyLevel(str(self.level).lower()))
        except ValueError:
            raise ConfigurationError(
                f"{self.level!r} is not a verification level.",
                hint="Use one of: " + ", ".join(v.value for v in VerifyLevel) + ".",
            ) from None
        expected = self.expected_checksum
        if expected is not None:
            expected = expected.strip().lower()
            if not _HEX.match(expected):
                raise ConfigurationError("The expected checksum must be written in hexadecimal.")
            object.__setattr__(self, "expected_checksum", expected)
        algorithm = self.checksum.strip().lower() if self.checksum else None
        if algorithm is None and expected is not None:
            algorithm = infer_algorithm(expected)
            if algorithm is None:
                raise ConfigurationError(
                    "The checksum algorithm could not be told from the expected checksum.",
                    hint="Set checksum to one of: " + ", ".join(CHECKSUM_ALGORITHMS) + ".",
                )
        if algorithm is not None and algorithm not in CHECKSUM_ALGORITHMS:
            raise ConfigurationError(
                f"{algorithm!r} is not a supported checksum.",
                hint="Use one of: " + ", ".join(CHECKSUM_ALGORITHMS) + ".",
            )
        if (
            expected is not None
            and algorithm is not None
            and len(expected) != (CHECKSUM_ALGORITHMS[algorithm])
        ):
            raise ConfigurationError(
                f"A {algorithm} checksum has {CHECKSUM_ALGORITHMS[algorithm]} characters, "
                f"but the expected one has {len(expected)}."
            )
        object.__setattr__(self, "checksum", algorithm)

    @property
    def requested(self) -> bool:
        """Whether anything is checked after the file is finished."""
        return self.level is not VerifyLevel.NONE or self.checksum is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "checksum": self.checksum,
            "expected_checksum": self.expected_checksum,
            "keep_invalid": self.keep_invalid,
            "ffprobe_path": str(self.ffprobe_path) if self.ffprobe_path else None,
        }
