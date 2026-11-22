"""Read and change the defaults new downloads start with."""

from typing import Annotated

from fastapi import APIRouter, Depends
from rayohx.config.download import MAX_CONCURRENCY

from rayohx_api.config import Settings, get_settings
from rayohx_api.schemas.v1.common import MIN_CONCURRENCY
from rayohx_api.schemas.v1.settings import Limits, SettingsUpdate, SettingsView

router = APIRouter()


def _view(settings: Settings) -> SettingsView:
    from rayohx import __version__

    from rayohx_api.routers.v1.deps import prefs

    p = prefs()
    return SettingsView(
        download_dir=str(settings.download_dir),
        max_active_downloads=settings.max_active_downloads,
        allow_local_paths=settings.allow_local_paths,
        concurrency=p.concurrency,
        quality=p.quality,
        overwrite=p.overwrite,
        limits=Limits(min_concurrency=MIN_CONCURRENCY, max_concurrency=MAX_CONCURRENCY),
        version=__version__,
    )


@router.get("/settings", summary="Current defaults")
async def read_settings(settings: Annotated[Settings, Depends(get_settings)]) -> SettingsView:
    return _view(settings)


@router.patch("/settings", summary="Change defaults")
async def update_settings(
    body: SettingsUpdate, settings: Annotated[Settings, Depends(get_settings)]
) -> SettingsView:
    from rayohx_api.routers.v1.deps import prefs

    prefs().update(body.model_dump(exclude_none=True))
    return _view(settings)
