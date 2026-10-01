from dataclasses import asdict
from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.config import get_thresholds
from app.routers.dependencies import SessionDep
from app.schemas import SnapIn, SnapOut
from app.services.cadastre import parcel_at
from app.services.property_snap import snap_to_property_lines

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


@router.post("/snap", response_model=SnapOut)
def snap(session: SessionDep, body: SnapIn):
    """A hand-drawn outline fitted to the property lines, or unchanged (docs/08-cadastre.md)."""
    with httpx.Client() as client:
        result = snap_to_property_lines(
            session, client, get_thresholds()["cadastre"], body.geometry
        )
    return asdict(result)
