from datetime import UTC, datetime

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import REPO_ROOT, get_thresholds
from app.routers.dependencies import OwnerDep
from app.schemas import DetectIn, DetectOut
from app.vision.field_detection import DetectionError, detect_field

router = APIRouter(prefix="/fields", tags=["fields"])

CACHE_DIR = REPO_ROOT / "data" / "cache" / "sentinel2"


@router.post("/detect", response_model=DetectOut)
def detect(_: OwnerDep, body: DetectIn):
    """The outline of the field under a point, from a year of Sentinel-2 images (docs/10)."""
    config = get_thresholds()["field_detection"]
    try:
        with httpx.Client() as client:
            found = detect_field(
                client, body.lat, body.lon, config, datetime.now(UTC).date(), CACHE_DIR
            )
    except DetectionError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc), "code": exc.code})
    return DetectOut(
        geometry=found.geometry, dates=len(found.dates), first=found.dates[0], last=found.dates[-1]
    )
