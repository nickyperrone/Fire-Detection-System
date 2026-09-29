from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FieldRiskEvent, FireEvent, FireEventStatus, RiskStatus, Territory


def list_fire_events(session: Session, status: FireEventStatus | None) -> list[FireEvent]:
    query = select(FireEvent).order_by(FireEvent.last_detected_at.desc())
    if status is not None:
        query = query.where(FireEvent.status == status)
    return list(session.scalars(query))


def list_risk_events(session: Session, owner: str, territory_id: int) -> list[FieldRiskEvent]:
    return list(
        session.scalars(
            select(FieldRiskEvent)
            .join(Territory)
            .where(Territory.owner == owner, FieldRiskEvent.territory_id == territory_id)
            .order_by(FieldRiskEvent.updated_at.desc())
        )
    )


def set_risk_status(
    session: Session, owner: str, risk_id: int, status: RiskStatus
) -> FieldRiskEvent | None:
    risk = session.scalar(
        select(FieldRiskEvent)
        .join(Territory)
        .where(Territory.owner == owner, FieldRiskEvent.id == risk_id)
    )
    if risk is not None:
        risk.status = status
        session.commit()
    return risk


def geojson(geom) -> dict:
    return mapping(to_shape(geom))
