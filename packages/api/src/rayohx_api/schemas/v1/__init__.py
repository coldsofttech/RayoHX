"""Request and response models for ``/api/v1``."""

from rayohx_api.schemas.v1.clean import CleanedFolder, CleanRequest, CleanResponse
from rayohx_api.schemas.v1.common import QUALITY, Network
from rayohx_api.schemas.v1.downloads import DownloadCreate, Job, JobList, Progress
from rayohx_api.schemas.v1.inspect import InspectRequest, InspectResponse
from rayohx_api.schemas.v1.settings import SettingsUpdate, SettingsView

__all__ = [
    "QUALITY",
    "CleanRequest",
    "CleanResponse",
    "CleanedFolder",
    "DownloadCreate",
    "InspectRequest",
    "InspectResponse",
    "Job",
    "JobList",
    "Network",
    "Progress",
    "SettingsUpdate",
    "SettingsView",
]
