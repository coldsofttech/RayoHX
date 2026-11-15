"""Typed, validated settings.

Every object is immutable and checks itself on creation, so a bad value fails at the edge with a
``ConfigurationError`` instead of deep inside a download. Secrets are kept out of ``repr`` and out
of ``as_dict``. Each area lives in its own module (``proxy``, ``network``, ``storage``, ``output``,
``selection`` and ``download``) and is also available here, for example
``rayohx.config.NetworkConfig``.
"""

from rayohx.config.download import DownloadConfig
from rayohx.config.network import NetworkConfig
from rayohx.config.output import OutputConfig
from rayohx.config.proxy import ProxyConfig
from rayohx.config.selection import SelectionConfig
from rayohx.config.storage import StorageConfig
from rayohx.config.url import validate_url

__all__ = [
    "DownloadConfig",
    "NetworkConfig",
    "OutputConfig",
    "ProxyConfig",
    "SelectionConfig",
    "StorageConfig",
    "validate_url",
]
