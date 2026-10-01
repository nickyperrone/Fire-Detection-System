from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.config import get_thresholds
from app.routers.dependencies import SessionDep
from app.services.cadastre import parcel_at

router = APIRouter(prefix="/cadastre", tags=["cadastre"])


@router.get("/parcel")
def parcel(
    session: SessionDep,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
) -> dict:
    """The official parcel at a point, to draw a field from it (docs/08-cadastre.md)."""
    with httpx.Client() as client:
        feature = parcel_at(session, client, get_thresholds()["cadastre"], lat, lon)
    if feature is None:
        raise HTTPException(404, "no parcel here")
    return feature
