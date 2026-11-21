"""Address checks shared by the settings and the request models."""


def validate_url(url: str, *, name: str = "url") -> str:
    """Return ``url`` stripped, or raise if it is not an absolute http(s) address."""
    from urllib.parse import urlsplit

    from rayohx.errors import ConfigurationError

    cleaned = url.strip()
    if any(ord(char) < 32 for char in cleaned):
        raise ConfigurationError(f"{name} contains control characters.")
    try:
        parts = urlsplit(cleaned)
        hostname = parts.hostname
    except ValueError as exc:
        raise ConfigurationError(f"{name} is not a valid address.") from exc
    if parts.scheme.lower() not in {"http", "https"} or not hostname:
        raise ConfigurationError(
            f"{name} must be an absolute http or https address.",
            hint="Example: https://example.com/master.m3u8",
        )
    return cleaned
