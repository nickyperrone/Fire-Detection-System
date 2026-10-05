"""All fields and sections with their three answers, worst first."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import (
    DataQuality,
    FieldRiskEvent,
    FireEvent,
    FireEventStatus,
    FireForecast,
    Observation,
    ObservationEventLink,
    Priority,
    RiskStatus,
    Severity,
    SprayAssessment,
    SprayStatus,
    Territory,
)
from app.services.data_quality import fire_quality, source_statuses, spray_quality
from app.services.field_risk import SEVERITY_RANK, compass
from app.services.lightning import NearbyLightning, nearby_lightning
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
    # Rules that did not pass for the current hour, as stored (see spray_rules.RuleResult).
    problems: list[dict] = field(default_factory=list)
    drift_toward: str | None = None
    next_favorable: tuple[datetime, datetime] | None = None


@dataclass
class LightningAnswer:
    data_quality: DataQuality
    window_minutes: int
    flashes: int = 0
    nearest_m: float | None = None
    last_at: datetime | None = None


@dataclass
class ForecastDay:
    horizon_days: int
    valid_from: date
    probability: float
    band: str
    factors: list[dict]


@dataclass
class ForecastAnswer:
    data_quality: DataQuality
    issued_at: datetime | None = None
    days: list[ForecastDay] = field(default_factory=list)


@dataclass
class WeatherAnswer:
    """The weather at the field's forecast point now, and rain in the next 24 hours."""

    data_quality: DataQuality
    valid_at: datetime | None = None
    temperature_c: float | None = None
    relative_humidity_pct: float | None = None
    wind_speed_kmh: float | None = None
    # Where the wind comes from, as in any forecast.
    wind_from: str | None = None
    wind_gusts_kmh: float | None = None
    cloud_cover_pct: float | None = None
    rain_24h_mm: float | None = None
    rain_probability_pct: float | None = None


@dataclass
class AnomalyPatch:
    kind: str
    area_ha: float
    where: str


@dataclass
class AnomalyAnswer:
    """Unusual patches on the field's latest clear date (docs/11-field-anomalies.md)."""

    data_quality: DataQuality = DataQuality.NO_DATA
    observed_on: date | None = None
    patches: list[AnomalyPatch] = field(default_factory=list)


@dataclass
class PortfolioEntry:
    territory: Territory
    fire: FireAnswer
    spray: SprayAnswer
    weather: WeatherAnswer
    lightning: LightningAnswer
    forecast: ForecastAnswer
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
    goes = thresholds["goes"]
    statuses = source_statuses(session, "firms", thresholds["firms"]["products"])
    statuses += source_statuses(session, "goes", [goes["fire_product"]])
    fire_dq = fire_quality(statuses, quality["fire_stale_after_hours"], now)
    lightning_dq = fire_quality(
        source_statuses(session, "goes", [goes["lightning_product"]]),
        quality["lightning_stale_after_minutes"] / 60,
        now,
    )
    lightning = nearby_lightning(session, ids, thresholds["lightning"], now)
    forecasts = _forecasts(session, ids)
    reads = [s.last_success_at for s in statuses if s.last_success_at is not None]
    last_read_at = max(reads) if reads else None
    risks = _open_risks(session, ids)
    received = _received_at(session, {r.fire_event_id for rs in risks.values() for r in rs})
    assessments = _assessments(session, ids, profile, now)
    anomalies = _anomalies(session, ids)
    entries = [
        PortfolioEntry(
            territory=t,
            fire=_fire_answer(risks.get(t.id, []), received, fire_dq, last_read_at),
            spray=_spray_answer(assessments.get(t.id, []), profile, quality, now),
            weather=_weather_answer(assessments.get(t.id, []), quality, now),
            lightning=_lightning_answer(
                lightning.get(t.id), lightning_dq, thresholds["lightning"]["window_minutes"]
            ),
            forecast=forecasts.get(t.id, ForecastAnswer(data_quality=DataQuality.NO_DATA)),
            anomaly=anomalies.get(t.id, AnomalyAnswer()),
        )
        for t in territories
    ]
    return _worst_first(entries)


# A lot takes its field's check, and the patches of its field that reach into it.
ANOMALIES_SQL = text("""
    SELECT t.id AS territory_id, c.data_quality, c.last_clear,
           a.kind, a.where, a.area_ha
    FROM territory t
    JOIN field_anomaly_check c ON c.territory_id = coalesce(t.parent_id, t.id)
    LEFT JOIN field_anomaly a
      ON a.territory_id = c.territory_id
     AND (t.parent_id IS NULL OR ST_Intersects(a.geom, t.geom))
    WHERE t.id = ANY(:ids)
    ORDER BY t.id, a.area_ha DESC
""")


def _anomalies(session: Session, ids: list[int]) -> dict[int, AnomalyAnswer]:
    answers: dict[int, AnomalyAnswer] = {}
    for row in session.execute(ANOMALIES_SQL, {"ids": ids}):
        answer = answers.setdefault(
            row.territory_id,
            AnomalyAnswer(data_quality=DataQuality(row.data_quality), observed_on=row.last_clear),
        )
        if row.kind is not None:
            answer.patches.append(AnomalyPatch(row.kind, row.area_ha, row.where))
    return answers


def _forecasts(session: Session, ids: list[int]) -> dict[int, ForecastAnswer]:
    rows = session.scalars(
        select(FireForecast)
        .where(FireForecast.territory_id.in_(ids))
        .order_by(FireForecast.horizon_days)
    ).all()
    answers: dict[int, ForecastAnswer] = {}
    for r in rows:
        answer = answers.setdefault(
            r.territory_id, ForecastAnswer(data_quality=r.data_quality, issued_at=r.issued_at)
        )
        answer.days.append(
            ForecastDay(r.horizon_days, r.valid_from, r.probability, r.band, r.factors)
        )
    return answers


def _lightning_answer(
    nearby: NearbyLightning | None, dq: DataQuality, window_minutes: int
) -> LightningAnswer:
    answer = LightningAnswer(data_quality=dq, window_minutes=window_minutes)
    if nearby:
        answer.flashes = nearby.flashes
        answer.nearest_m = nearby.nearest_m
        answer.last_at = nearby.last_at
    return answer


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
    answer.problems = [r for r in current.rules if r["status"] != "PASS"]
    answer.drift_toward = drift_direction(current.weather.get("wind_direction_deg"))
    answer.next_favorable = next_favorable_window(assessments)
    return answer


# Hours of rain counted ahead in the weather answer.
RAIN_HOURS = 24


def _weather_answer(
    assessments: list[SprayAssessment], quality: dict, now: datetime
) -> WeatherAnswer:
    """From the same hourly forecast as the spray answer, so the two never disagree."""
    current = assessments[0] if assessments else None
    answer = WeatherAnswer(
        data_quality=spray_quality(current, quality["weather_stale_after_hours"], now)
    )
    if current is None:
        return answer
    w = current.weather
    ahead = [a.weather for a in assessments[:RAIN_HOURS]]
    rain = [h["precipitation_mm"] for h in ahead if h.get("precipitation_mm") is not None]
    chance = [
        h["precipitation_probability_pct"]
        for h in ahead
        if h.get("precipitation_probability_pct") is not None
    ]
    answer.valid_at = current.valid_at
    answer.temperature_c = w.get("temperature_c")
    answer.relative_humidity_pct = w.get("relative_humidity_pct")
    answer.wind_speed_kmh = w.get("wind_speed_kmh")
    answer.wind_from = compass(w.get("wind_direction_deg"))
    answer.wind_gusts_kmh = w.get("wind_gusts_kmh")
    answer.cloud_cover_pct = w.get("cloud_cover_pct")
    answer.rain_24h_mm = round(sum(rain), 1) if rain else None
    answer.rain_probability_pct = max(chance) if chance else None
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


PRIORITY_RANK = {Priority.HIGH: 0, Priority.NORMAL: 1, Priority.LOW: 2}


def _worst_first(entries: list[PortfolioEntry]) -> list[PortfolioEntry]:
    """Groups a field with its sections, and orders groups by the field's priority, then by their
    worst fire severity."""
    groups: dict[int, list[PortfolioEntry]] = defaultdict(list)
    for entry in entries:
        groups[entry.territory.parent_id or entry.territory.id].append(entry)

    def rank(entry: PortfolioEntry) -> int:
        return SEVERITY_RANK[entry.fire.severity] if entry.fire.severity else -1

    ordered = sorted(
        groups.values(),
        key=lambda g: (
            PRIORITY_RANK[g[0].territory.priority],
            -max(rank(e) for e in g),
            g[0].territory.name,
        ),
    )
    return [e for group in ordered for e in group]
