"""Look at a playlist without downloading it."""

from fastapi import APIRouter, status

from rayohx_api.schemas.v1.inspect import InspectRequest, InspectResponse

router = APIRouter()


@router.post("/inspect", summary="Look at a playlist without downloading it")
async def inspect_playlist(body: InspectRequest) -> InspectResponse:
    import asyncio

    from rayohx.config import NetworkConfig
    from rayohx.errors import RayoHXError
    from rayohx.playlist.inspection import inspect
    from rayohx.serialization import playlist_to_dict

    from rayohx_api.routers.v1.deps import problem

    network = NetworkConfig(headers=dict(body.network.headers))
    try:
        playlist = await asyncio.to_thread(inspect, body.url, network)
    except RayoHXError as exc:
        raise problem(status.HTTP_422_UNPROCESSABLE_CONTENT, exc) from exc
    return InspectResponse(playlist=playlist_to_dict(playlist))
