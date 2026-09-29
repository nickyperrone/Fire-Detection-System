from fastapi import APIRouter, HTTPException

from app.models import FireEventStatus
from app.routers.dependencies import SessionDep, SettingsDep
from app.schemas import FireEventOut, RiskStatusIn
from app.services.fire_events import geojson, list_fire_events, set_risk_status

router = APIRouter(tags=["fires"])


@router.get("/fire-events", response_model=list[FireEventOut])
def fire_events(
    session: SessionDep,
    status: FireEventStatus | None = FireEventStatus.ACTIVE,
):
    return [
        FireEventOut(
            id=e.id,
            status=e.status,
            first_detected_at=e.first_detected_at,
            last_detected_at=e.last_detected_at,
            observation_count=e.observation_count,
            confidence=e.confidence.value,
            max_frp_mw=e.max_frp_mw,
            sensors=e.sensors,
            processing_version=e.processing_version,
            geometry=geojson(e.geom),
        )
        for e in list_fire_events(session, status)
    ]


@router.patch("/risk-events/{risk_id}", status_code=204)
def update_risk_status(
    session: SessionDep,
    settings: SettingsDep,
    risk_id: int,
    body: RiskStatusIn,
):
    if set_risk_status(session, settings.owner, risk_id, body.status) is None:
        raise HTTPException(404, "risk event not found")
