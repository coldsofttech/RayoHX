"""Read and change the defaults new downloads start with."""

from typing import Annotated

from fastapi import APIRouter, Depends

from rayohx_api.config import Settings, get_settings
from rayohx_api.schemas.v1.settings import SettingsUpdate, SettingsView

router = APIRouter()


def _view(settings: Settings) -> SettingsView:
    from rayohx import __version__

    from rayohx_api.routers.v1.deps import prefs

    p = prefs()
    return SettingsView(
        download_dir=str(settings.download_dir),
        max_active_downloads=settings.max_active_downloads,
        concurrency=p.concurrency,
        quality=p.quality,
        overwrite=p.overwrite,
        version=__version__,
    )


@router.get("/settings", summary="Current defaults")
async def read_settings(settings: Annotated[Settings, Depends(get_settings)]) -> SettingsView:
    return _view(settings)


@router.patch("/settings", summary="Change defaults for this run")
async def update_settings(
    body: SettingsUpdate, settings: Annotated[Settings, Depends(get_settings)]
) -> SettingsView:
    from rayohx_api.routers.v1.deps import prefs

    p = prefs()
    for name, value in body.model_dump(exclude_none=True).items():
        setattr(p, name, value)
    return _view(settings)
