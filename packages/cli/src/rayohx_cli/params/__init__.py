"""The command line's options, defined once and shared by every command that takes them.

Every option that takes one value can also be set with a ``RAYOHX_<NAME>`` environment variable
(``RAYOHX_QUALITY``, ``RAYOHX_PROXY``) or in the settings file; the command line wins over both.
"""

from rayohx_cli.params.display import (
    JsonOutput,
    ProgressMode,
)
from rayohx_cli.params.engine import (
    BufferSize,
    Concurrency,
    MaxTempSize,
    Resume,
    Storage,
    Workspace,
)
from rayohx_cli.params.network import (
    CaBundle,
    ConnectTimeout,
    Cookie,
    CredentialHost,
    Header,
    Insecure,
    Origin,
    Proxy,
    RateLimit,
    ReadTimeout,
    Referer,
    Retries,
    Timeout,
    UserAgent,
)
from rayohx_cli.params.output import (
    Ffmpeg,
    Format,
    OutputPath,
    Overwrite,
    RemuxBackendOption,
    Validate,
)
from rayohx_cli.params.selection import (
    Audio,
    AudioName,
    MaxBitrate,
    MaxResolution,
    Quality,
    SubtitleName,
    Subtitles,
    Url,
    VideoOnly,
)

__all__ = [
    "Audio",
    "AudioName",
    "BufferSize",
    "CaBundle",
    "Concurrency",
    "ConnectTimeout",
    "Cookie",
    "CredentialHost",
    "Ffmpeg",
    "Format",
    "Header",
    "Insecure",
    "JsonOutput",
    "MaxBitrate",
    "MaxResolution",
    "MaxTempSize",
    "Origin",
    "OutputPath",
    "Overwrite",
    "ProgressMode",
    "Proxy",
    "Quality",
    "RateLimit",
    "ReadTimeout",
    "Referer",
    "RemuxBackendOption",
    "Resume",
    "Retries",
    "Storage",
    "SubtitleName",
    "Subtitles",
    "Timeout",
    "Url",
    "UserAgent",
    "Validate",
    "VideoOnly",
    "Workspace",
]
