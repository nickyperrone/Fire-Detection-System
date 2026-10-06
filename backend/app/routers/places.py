from dataclasses import asdict

import httpx
from fastapi import APIRouter, HTTPException, Query

from app.config import get_thresholds
from app.routers.dependencies import HttpDep
from app.schemas import PlaceOut
from app.services.places import find_places

router = APIRouter(tags=["places"])


@router.get("/places", response_model=list[PlaceOut])
def places(http: HttpDep, q: str = Query(max_length=120)):
    """Addresses, streets, towns and areas in Argentina for the search box (docs/04)."""
    try:
        return [asdict(p) for p in find_places(http, get_thresholds()["places"], q)]
    except httpx.HTTPError as exc:
        raise HTTPException(503, "place search unavailable") from exc
