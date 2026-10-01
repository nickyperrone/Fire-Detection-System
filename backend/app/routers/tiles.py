from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Path, Response

from app.config import get_thresholds
from app.routers.dependencies import SessionDep, SettingsDep
from app.services.cadastre import ensure_tile
from app.services.tiles import Layer, build_tile

router = APIRouter(tags=["tiles"])

MVT_MEDIA_TYPE = "application/vnd.mapbox-vector-tile"
# Fires change with each ingestion (every 5 min). Fields change only when the user edits them,
# and the frontend adds a version parameter to the tile URL after every edit.
CACHE_CONTROL = {
    Layer.TERRITORIES: "private, max-age=60",
    Layer.FIRE_EVENTS: "public, max-age=300",
    Layer.OBSERVATIONS: "public, max-age=300",
    # New flashes arrive every 20 seconds.
    Layer.LIGHTNING: "public, max-age=30",
    # The forecast is reissued every hour.
    Layer.RISK: "public, max-age=600",
    # Parcels change in months, not hours.
    Layer.PARCELS: "public, max-age=86400",
}


@router.get("/tiles/{layer}/{z}/{x}/{y}.pbf", response_class=Response)
def tile(
    session: SessionDep,
    settings: SettingsDep,
    layer: Layer,
    z: Annotated[int, Path(ge=0, le=22)],
    x: Annotated[int, Path(ge=0)],
    y: Annotated[int, Path(ge=0)],
):
    if x >= 2**z or y >= 2**z:
        raise HTTPException(404, "tile outside the zoom level")
    thresholds = get_thresholds()
    if layer == Layer.PARCELS:
        # First view of an area fetches its parcels from the province; then they are cached.
        with httpx.Client() as client:
            ensure_tile(session, client, thresholds["cadastre"], z, x, y)
    west, south = thresholds["region"]["bbox"][:2]
    content = build_tile(
        session,
        layer,
        z,
        x,
        y,
        settings.owner,
        datetime.now(UTC),
        thresholds["lightning"]["window_minutes"],
        (west, south, thresholds["forecast"]["cell_degrees"]),
    )
    headers = {"Cache-Control": CACHE_CONTROL[layer]}
    if not content:
        return Response(status_code=204, headers=headers)
    return Response(content, media_type=MVT_MEDIA_TYPE, headers=headers)
