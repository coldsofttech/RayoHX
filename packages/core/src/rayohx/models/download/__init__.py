"""Models that describe a download: the request, its progress and its result."""

from rayohx.models.download.output import OutputInfo
from rayohx.models.download.progress import DownloadProgress
from rayohx.models.download.request import DownloadRequest
from rayohx.models.download.result import DownloadResult
from rayohx.models.download.storage import StorageMetrics

__all__ = [
    "DownloadProgress",
    "DownloadRequest",
    "DownloadResult",
    "OutputInfo",
    "StorageMetrics",
]
