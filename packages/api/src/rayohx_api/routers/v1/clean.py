"""Remove working folders left by interrupted downloads."""

from typing import Annotated

from fastapi import APIRouter, Depends

from rayohx_api.config import Settings, get_settings
from rayohx_api.schemas.v1.clean import CleanRequest, CleanResponse

router = APIRouter()


@router.post("/clean", summary="Remove working folders left by interrupted downloads")
async def clean(
    body: CleanRequest, settings: Annotated[Settings, Depends(get_settings)]
) -> CleanResponse:
    """Only looks inside the download folder. Folders of running downloads are never removed."""
    import asyncio

    from rayohx.workspaces import find_workspaces, remove_workspaces

    from rayohx_api.schemas.v1.clean import CleanedFolder

    found = await asyncio.to_thread(find_workspaces, [settings.download_dir], body.older_than_days)
    idle = [w for w in found if not w.in_use]
    if not body.dry_run:
        await asyncio.to_thread(remove_workspaces, idle)
    folders = [
        CleanedFolder(name=w.path.name, size_bytes=w.size, age_days=round(w.age_days, 2))
        for w in idle
    ]
    return CleanResponse(
        dry_run=body.dry_run,
        folders=folders,
        freed_bytes=sum(f.size_bytes for f in folders),
        skipped_in_use=len(found) - len(idle),
    )
