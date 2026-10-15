from dataclasses import asdict

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.config import get_thresholds
from app.routers.dependencies import HttpDep
from app.schemas import PlaceOut
from app.services.captcha import RateLimit, client_ip, limit_key
from app.services.places import find_places

searches = RateLimit()

router = APIRouter(tags=["places"])


@router.get("/places", response_model=list[PlaceOut])
def places(request: Request, http: HttpDep, q: str = Query(max_length=120)):
    """Addresses, streets, towns and areas in Argentina for the search box (docs/04). Limited
    per network address: the search service behind it is shared and free."""
    ip = client_ip(request.headers, request.client.host if request.client else None)
    if not searches.allow(limit_key(ip), get_thresholds()["places"]["per_ip_hour"]):
        return JSONResponse(
            status_code=429, content={"detail": "too many searches", "code": "too_many"}
        )
    try:
        return [asdict(p) for p in find_places(http, get_thresholds()["places"], q)]
    except httpx.HTTPError as exc:
        raise HTTPException(503, "place search unavailable") from exc
