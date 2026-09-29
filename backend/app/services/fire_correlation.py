"""Group observations of the same fire into fire events (docs/03-rules.md#fire-correlation)."""

from datetime import datetime, timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.models import (
    Confidence,
    FireEvent,
    FireEventStatus,
    Observation,
    ObservationEventLink,
)

CONFIDENCE_RANK = {Confidence.LOW: 0, Confidence.NOMINAL: 1, Confidence.HIGH: 2}

# Time gap is 0 inside the event's [first, last] window, so late-arriving older passes still join.
CANDIDATES_SQL = text("""
    SELECT fe.id,
           ST_Distance(fe.geom::geography, o.geom::geography) AS distance_m,
           EXTRACT(EPOCH FROM GREATEST(
               o.acquired_at - fe.last_detected_at,
               fe.first_detected_at - o.acquired_at,
               interval '0'
           )) / 3600 AS time_gap_h
    FROM fire_event fe, observation o
    WHERE o.id = :observation_id
      AND fe.status = 'ACTIVE'
      AND ST_DWithin(fe.geom::geography, o.geom::geography, :max_distance_m)
      AND o.acquired_at <= fe.last_detected_at + make_interval(hours => :max_gap_h)
      AND o.acquired_at >= fe.first_detected_at - make_interval(hours => :max_gap_h)
    ORDER BY distance_m
""")


def sensor_label(observation: Observation) -> str:
    return f"{observation.sensor} {observation.satellite}"


def correlate(session: Session, config: dict, version: str, now: datetime) -> set[int]:
    """Link every unlinked observation to a fire event. Returns the ids of events that changed."""
    unlinked = session.scalars(
        select(Observation)
        .outerjoin(ObservationEventLink)
        .where(ObservationEventLink.observation_id.is_(None))
        .order_by(Observation.acquired_at, Observation.id)
    ).all()
    changed: set[int] = set()
    for observation in unlinked:
        candidates = session.execute(
            CANDIDATES_SQL,
            {
                "observation_id": observation.id,
                "max_distance_m": config["max_distance_m"],
                "max_gap_h": config["max_time_gap_hours"],
            },
        ).all()
        if candidates:
            event = session.get(FireEvent, candidates[0].id)
            _extend(session, event, observation, version, now)
            reason = {
                "rule": config["rule"],
                "distance_m": round(candidates[0].distance_m, 1),
                "time_gap_h": round(float(candidates[0].time_gap_h), 2),
                "candidates": len(candidates),
            }
        else:
            event = _start(session, observation, version)
            reason = {"rule": config["rule"], "new_event": True, "candidates": 0}
        session.add(
            ObservationEventLink(
                observation_id=observation.id,
                fire_event_id=event.id,
                reason=reason,
                processing_version=version,
            )
        )
        session.flush()
        changed.add(event.id)
    mark_stale(session, config["stale_after_hours"], now)
    session.commit()
    return changed


def _start(session: Session, observation: Observation, version: str) -> FireEvent:
    event = FireEvent(
        geom=observation.geom,
        first_detected_at=observation.acquired_at,
        last_detected_at=observation.acquired_at,
        observation_count=1,
        confidence=observation.confidence,
        max_frp_mw=observation.frp_mw,
        sensors=[sensor_label(observation)],
        status=FireEventStatus.ACTIVE,
        processing_version=version,
    )
    session.add(event)
    session.flush()
    return event


def _extend(
    session: Session, event: FireEvent, observation: Observation, version: str, now: datetime
) -> None:
    event.first_detected_at = min(event.first_detected_at, observation.acquired_at)
    event.last_detected_at = max(event.last_detected_at, observation.acquired_at)
    event.observation_count += 1
    if CONFIDENCE_RANK[observation.confidence] > CONFIDENCE_RANK[event.confidence]:
        event.confidence = observation.confidence
    frps = [v for v in (event.max_frp_mw, observation.frp_mw) if v is not None]
    event.max_frp_mw = max(frps) if frps else None
    label = sensor_label(observation)
    if label not in event.sensors:
        event.sensors = [*event.sensors, label]
    event.processing_version = version
    event.updated_at = now
    session.flush()
    session.execute(
        update(FireEvent)
        .where(FireEvent.id == event.id)
        .values(geom=func.ST_ConvexHull(func.ST_Collect(FireEvent.geom, observation.geom)))
    )
    session.refresh(event, ["geom"])


def mark_stale(session: Session, stale_after_hours: float, now: datetime) -> None:
    session.execute(
        update(FireEvent)
        .where(
            FireEvent.status == FireEventStatus.ACTIVE,
            FireEvent.last_detected_at < now - timedelta(hours=stale_after_hours),
        )
        .values(status=FireEventStatus.STALE, updated_at=now)
    )
