"""Impact of each fire event on each nearby field and section (docs/03-rules.md#field-risk)."""

from datetime import datetime

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.models import FieldRiskEvent, FireEvent, FireEventStatus, RiskStatus, Severity
from app.services.wind import Push, Wind, push, wind_now

SEVERITY_RANK = {Severity.WATCH: 0, Severity.HIGH: 1, Severity.VERY_HIGH: 2, Severity.CRITICAL: 3}
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

NEARBY_TERRITORIES_SQL = text("""
    SELECT t.id AS territory_id,
           ST_Distance(t.geom::geography, fe.geom::geography) AS distance_m,
           ST_Intersects(t.geom, fe.geom) AS intersects,
           degrees(ST_Azimuth(
               ST_Centroid(t.geom)::geography, ST_Centroid(fe.geom)::geography
           )) AS bearing_deg
    FROM territory t, fire_event fe
    WHERE fe.id = :fire_event_id
      AND ST_DWithin(t.geom::geography, fe.geom::geography, :max_distance_m)
""")


def severity_for(distance_m: float, intersects: bool, bands: list[dict]) -> Severity | None:
    if intersects:
        return Severity.CRITICAL
    for band in bands:
        if band["max_distance_m"] > 0 and distance_m < band["max_distance_m"]:
            return Severity(band["severity"])
    return None


def raised(severity: Severity, by: int) -> Severity:
    """Moved `by` bands closer to danger, never to CRITICAL: that one means the fire is inside."""
    order = sorted(SEVERITY_RANK, key=SEVERITY_RANK.get)
    return order[min(SEVERITY_RANK[severity] + by, SEVERITY_RANK[Severity.VERY_HIGH])]


def compass(bearing_deg: float | None) -> str | None:
    if bearing_deg is None:
        return None
    return COMPASS[round(bearing_deg / 45) % 8]


def assess_active_fire_events(session: Session, config: dict, version: str, now: datetime) -> int:
    """Every active fire against every territory, so new and edited fields are included."""
    ids = set(
        session.scalars(select(FireEvent.id).where(FireEvent.status == FireEventStatus.ACTIVE))
    )
    return assess_fire_events(session, ids, config, version, now)


def reassess_territory(
    session: Session, territory_id: int, config: dict, version: str, now: datetime
) -> None:
    """After an outline edit: every active fire again, and none that is no longer in range."""
    assess_active_fire_events(session, config, version, now)
    session.execute(
        delete(FieldRiskEvent).where(
            FieldRiskEvent.territory_id == territory_id,
            FieldRiskEvent.updated_at < now,
            FieldRiskEvent.fire_event_id.in_(
                select(FireEvent.id).where(FireEvent.status == FireEventStatus.ACTIVE)
            ),
        )
    )
    session.commit()


def assess_fire_events(
    session: Session, fire_event_ids: set[int], config: dict, version: str, now: datetime
) -> int:
    """Create or update field risk events for the given active fire events. Returns rows touched."""
    bands = config["bands"]
    widest = max(band["max_distance_m"] for band in bands)
    events = session.scalars(
        select(FireEvent).where(
            FireEvent.id.in_(fire_event_ids), FireEvent.status == FireEventStatus.ACTIVE
        )
    ).all()
    nearby = {
        event.id: session.execute(
            NEARBY_TERRITORIES_SQL, {"fire_event_id": event.id, "max_distance_m": widest}
        ).all()
        for event in events
    }
    wind = wind_now(
        session, list({row.territory_id for rows in nearby.values() for row in rows}), now
    )
    touched = 0
    for event in events:
        for row in nearby[event.id]:
            severity = severity_for(row.distance_m, row.intersects, bands)
            if severity is None:
                continue
            here = wind.get(row.territory_id)
            pushed = push(here, row.bearing_deg, row.distance_m, config["wind"])
            if severity != Severity.CRITICAL:
                severity = raised(severity, pushed.raise_by)
            _upsert(session, event, row, severity, here, pushed, version, now)
            touched += 1
    session.commit()
    return touched


def _upsert(
    session: Session,
    event: FireEvent,
    row,
    severity: Severity,
    wind: Wind | None,
    pushed: Push,
    version: str,
    now: datetime,
):
    risk = session.scalar(
        select(FieldRiskEvent).where(
            FieldRiskEvent.territory_id == row.territory_id,
            FieldRiskEvent.fire_event_id == event.id,
        )
    )
    if risk is None:
        risk = FieldRiskEvent(
            territory_id=row.territory_id, fire_event_id=event.id, status=RiskStatus.NEW
        )
        session.add(risk)
    elif SEVERITY_RANK[severity] > SEVERITY_RANK[risk.severity]:
        # A fire getting closer is news again, even if the user already saw it.
        risk.status = RiskStatus.NEW
    risk.distance_m = row.distance_m
    risk.bearing_deg = row.bearing_deg
    risk.severity = severity
    risk.factors = {
        "distance_m": round(row.distance_m, 1),
        "confidence": event.confidence.value,
        "max_frp_mw": event.max_frp_mw,
        "sensor_count": len(event.sensors),
        "observation_count": event.observation_count,
        "wind_kmh": wind and round(wind.speed_kmh, 1),
        "wind_from_deg": wind and round(wind.from_deg),
        "wind_toward": pushed.toward,
        "wind_raised_by": pushed.raise_by,
        "arrival_h": pushed.arrival_h,
    }
    risk.processing_version = version
    risk.updated_at = now
