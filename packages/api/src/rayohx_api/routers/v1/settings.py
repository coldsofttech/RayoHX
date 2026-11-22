"""Read and change the defaults new downloads start with."""

from typing import Annotated

from fastapi import APIRouter, Depends

from rayohx_api.config import Settings, get_settings
from rayohx_api.schemas.v1.settings import SettingsUpdate, SettingsView

router = APIRouter()


def _view(settings: Settings) -> SettingsView:
    from rayohx import __version__
    from rayohx.config.download import MAX_CONCURRENCY

    from rayohx_api.routers.v1.deps import prefs
    from rayohx_api.schemas.v1.common import MIN_CONCURRENCY
    from rayohx_api.schemas.v1.settings import Limits

    p = prefs()
    return SettingsView(
        download_dir=str(p.download_dir),
        max_active_downloads=settings.max_active_downloads,
        allow_local_paths=settings.allow_local_paths,
        concurrency=p.concurrency,
        quality=p.quality,
        overwrite=p.overwrite,
        theme=p.theme,  # type: ignore[arg-type]
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
    from pathlib import Path

    from fastapi import HTTPException, status

    from rayohx_api.routers.v1.deps import manager, prefs

    changes = body.model_dump(exclude_none=True)
    if "download_dir" in changes:
        if not settings.allow_local_paths:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "The folder cannot be changed here.")
        folder = Path(changes["download_dir"])
        if not folder.is_absolute():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give a full folder path.")
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "That folder cannot be used."
            ) from exc
        changes["download_dir"] = folder
        manager().directory = folder
    prefs().update(changes)
    return _view(settings)
