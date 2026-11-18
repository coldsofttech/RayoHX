"""Removal of secrets from URLs, headers and free text before they are logged or shown.

This is the public face of the redactor. Front ends and the platform import from here, never from
the underscore module behind it.
"""

from rayohx._redaction import (
    REDACTED,
    SENSITIVE_HEADERS,
    is_sensitive_name,
    redact_headers,
    redact_text,
    redact_url,
)

__all__ = [
    "REDACTED",
    "SENSITIVE_HEADERS",
    "is_sensitive_name",
    "redact_headers",
    "redact_text",
    "redact_url",
]
