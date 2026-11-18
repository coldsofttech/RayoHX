"""Checking that a finished download is what it should be.

A download is not finished just because every request succeeded. Depending on ``VerifyConfig``
the finished file is checked for structure, looked into with ffprobe (when installed) and compared
with a checksum, and the result is an ``IntegrityReport`` that lists everything that was looked at
and everything that could not be.
"""

from rayohx.verify.checks import Expectations, verify_output
from rayohx.verify.checksum import file_checksum
from rayohx.verify.report import Check, CheckStatus, ChecksumResult, IntegrityReport

__all__ = [
    "Check",
    "CheckStatus",
    "ChecksumResult",
    "Expectations",
    "IntegrityReport",
    "file_checksum",
    "verify_output",
]
