from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import text

from app.config import get_thresholds
from app.routers.dependencies import SessionDep
from app.schemas import HealthOut
from app.services.data_quality import fire_quality, latest_pass, source_statuses
from app.versioning import processing_version

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health(session: SessionDep):
    thresholds = get_thresholds()
    session.execute(text("SELECT 1"))
    goes = thresholds["goes"]
    fire_statuses = source_statuses(session, "firms", thresholds["firms"]["products"])
    fire_statuses += source_statuses(session, "goes", [goes["fire_product"]])
    statuses = fire_statuses + source_statuses(session, "goes", [goes["lightning_product"]])
    statuses += source_statuses(session, "open_meteo", ["forecast"])
    return HealthOut(
        database=True,
        processing_version=processing_version(thresholds),
        fire_data_quality=fire_quality(
            fire_statuses, thresholds["data_quality"]["fire_stale_after_hours"], datetime.now(UTC)
        ),
        latest_pass=asdict(newest) if (newest := latest_pass(session)) else None,
        sources=[asdict(s) for s in statuses],
    )
