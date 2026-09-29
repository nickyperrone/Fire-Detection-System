"""All fields and sections with their three answers, worst first."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    DataQuality,
    FieldRiskEvent,
    FireEvent,
    FireEventStatus,
    Observation,
    ObservationEventLink,
    RiskStatus,
    Severity,
    SprayAssessment,
    SprayStatus,
    Territory,
)
from app.services.data_quality import fire_quality, source_statuses, spray_quality
from app.services.field_risk import SEVERITY_RANK, compass
from app.services.spray_rules import drift_direction
from app.services.territories import list_territories


@dataclass
class FireAnswer:
    data_quality: DataQuality
    last_read_at: datetime | None = None
    severity: Severity | None = None
    distance_m: float | None = None
    direction: str | None = None
    sensors: list[str] = field(default_factory=list)
    confidence: str | None = None
    acquired_at: datetime | None = None
    received_at: datetime | None = None
    fire_event_id: int | None = None
    other_fires: int = 0


@dataclass
class SprayAnswer:
    data_quality: DataQuality
    profile: str
    status: SprayStatus | None = None
    valid_at: datetime | None = None
    reasons: list[str] = field(default_factory=list)
    drift_toward: str | None = None
    next_favorable: tuple[datetime, datetime] | None = None


@dataclass
class AnomalyAnswer:
    data_quality: DataQuality = DataQuality.NO_DATA
    message: str = "imagery analysis starts in Phase 1"


@dataclass
class PortfolioEntry:
    territory: Territory
    fire: FireAnswer
    spray: SprayAnswer
    anomaly: AnomalyAnswer


def build_portfolio(
    session: Session,
    owner: str,
    thresholds: dict,
    now: datetime,
    tags: Sequence[str] = (),
    profile: str = "default",
) -> list[PortfolioEntry]:
    territories = list_territories(session, owner, tags)
    ids = [t.id for t in territories]
    quality = thresholds["data_quality"]
    statuses = source_statuses(session, "firms", thresholds["firms"]["products"])
    fire_dq = fire_quality(statuses, quality["fire_stale_after_hours"], now)
    reads = [s.last_success_at for s in statuses if s.last_success_at is not None]
    last_read_at = max(reads) if reads else None
    risks = _open_risks(session, ids)
    received = _received_at(session, {r.fire_event_id for rs in risks.values() for r in rs})
    assessments = _assessments(session, ids, profile, now)
    entries = [
        PortfolioEntry(
            territory=t,
            fire=_fire_answer(risks.get(t.id, []), received, fire_dq, last_read_at),
            spray=_spray_answer(assessments.get(t.id, []), profile, quality, now),
            anomaly=AnomalyAnswer(),
        )
        for t in territories
    ]
    return _worst_first(entries)


def _open_risks(session: Session, ids: list[int]) -> dict[int, list[FieldRiskEvent]]:
    rows = session.scalars(
        select(FieldRiskEvent)
        .join(FireEvent)
        .where(
            FieldRiskEvent.territory_id.in_(ids),
            FieldRiskEvent.status != RiskStatus.RESOLVED,
            FireEvent.status == FireEventStatus.ACTIVE,
        )
    ).all()
    by_territory = defaultdict(list)
    for risk in rows:
        by_territory[risk.territory_id].append(risk)
    for risks in by_territory.values():
        risks.sort(key=lambda r: (-SEVERITY_RANK[r.severity], r.distance_m))
    return by_territory


def _received_at(session: Session, fire_event_ids: set[int]) -> dict[int, datetime]:
    rows = session.execute(
        select(ObservationEventLink.fire_event_id, func.max(Observation.ingested_at))
        .join(Observation)
        .where(ObservationEventLink.fire_event_id.in_(fire_event_ids))
        .group_by(ObservationEventLink.fire_event_id)
    ).all()
    return dict(rows)


def _assessments(
    session: Session, ids: list[int], profile: str, now: datetime
) -> dict[int, list[SprayAssessment]]:
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    rows = session.scalars(
        select(SprayAssessment)
        .where(
            SprayAssessment.territory_id.in_(ids),
            SprayAssessment.profile == profile,
            SprayAssessment.valid_at >= current_hour,
        )
        .order_by(SprayAssessment.valid_at)
    ).all()
    by_territory = defaultdict(list)
    for assessment in rows:
        by_territory[assessment.territory_id].append(assessment)
    return by_territory


def _fire_answer(
    risks: list[FieldRiskEvent],
    received: dict[int, datetime],
    dq: DataQuality,
    last_read_at: datetime | None,
) -> FireAnswer:
    if not risks:
        return FireAnswer(data_quality=dq, last_read_at=last_read_at)
    worst = risks[0]
    event = worst.fire_event
    return FireAnswer(
        data_quality=dq,
        last_read_at=last_read_at,
        severity=worst.severity,
        distance_m=worst.distance_m,
        direction=compass(worst.bearing_deg),
        sensors=event.sensors,
        confidence=event.confidence.value,
        acquired_at=event.last_detected_at,
        received_at=received.get(event.id),
        fire_event_id=event.id,
        other_fires=len(risks) - 1,
    )


def _spray_answer(
    assessments: list[SprayAssessment], profile: str, quality: dict, now: datetime
) -> SprayAnswer:
    current = assessments[0] if assessments else None
    answer = SprayAnswer(
        data_quality=spray_quality(current, quality["weather_stale_after_hours"], now),
        profile=profile,
    )
    if current is None:
        return answer
    answer.status = current.status
    answer.valid_at = current.valid_at
    answer.reasons = [
        r["message"] for r in current.rules if r["status"] in ("FAIL", "CAUTION", "UNKNOWN")
    ]
    answer.drift_toward = drift_direction(current.weather.get("wind_direction_deg"))
    answer.next_favorable = next_favorable_window(assessments)
    return answer


def next_favorable_window(assessments: list[SprayAssessment]) -> tuple[datetime, datetime] | None:
    """First run of consecutive FAVORABLE hours, as [start, end)."""
    start = end = None
    for a in assessments:
        if a.status == SprayStatus.FAVORABLE:
            start = start or a.valid_at
            end = a.valid_at + timedelta(hours=1)
        elif start is not None:
            break
    return (start, end) if start else None


def _worst_first(entries: list[PortfolioEntry]) -> list[PortfolioEntry]:
    """Groups a field with its sections, and orders groups by their worst fire severity."""
    groups: dict[int, list[PortfolioEntry]] = defaultdict(list)
    for entry in entries:
        groups[entry.territory.parent_id or entry.territory.id].append(entry)

    def rank(entry: PortfolioEntry) -> int:
        return SEVERITY_RANK[entry.fire.severity] if entry.fire.severity else -1

    ordered = sorted(
        groups.values(),
        key=lambda g: (-max(rank(e) for e in g), g[0].territory.name),
    )
    return [e for group in ordered for e in group]
