from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import text

from app.config import get_thresholds
from app.routers.dependencies import SessionDep
from app.schemas import HealthOut
from app.services.data_quality import fire_quality, source_statuses
from app.versioning import processing_version

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health(session: SessionDep):
    thresholds = get_thresholds()
    session.execute(text("SELECT 1"))
    statuses = source_statuses(session, "firms", thresholds["firms"]["products"])
    statuses += source_statuses(session, "open_meteo", ["forecast"])
    firms_statuses = [s for s in statuses if s.provider == "firms"]
    return HealthOut(
        database=True,
        processing_version=processing_version(thresholds),
        fire_data_quality=fire_quality(
            firms_statuses, thresholds["data_quality"]["fire_stale_after_hours"], datetime.now(UTC)
        ),
        sources=[asdict(s) for s in statuses],
    )
