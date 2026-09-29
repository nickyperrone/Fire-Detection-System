from dataclasses import asdict
from datetime import datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import DataQuality, IngestionRun, RunStatus, SprayAssessment, Territory
from app.providers import open_meteo
from app.providers.records import PointForecast
from app.services.spray_rules import RuleStatus, evaluate_hour

# Keeps the Open-Meteo URL short; the API accepts many more points per request.
POINTS_PER_REQUEST = 50


def grid_point(latitude: float, longitude: float, grid: float) -> tuple[float, float]:
    return round(round(latitude / grid) * grid, 4), round(round(longitude / grid) * grid, 4)


def territory_points(session: Session, grid: float) -> dict[int, tuple[float, float]]:
    rows = session.execute(
        select(
            Territory.id,
            func.ST_Y(func.ST_Centroid(Territory.geom)),
            func.ST_X(func.ST_Centroid(Territory.geom)),
        )
    ).all()
    return {row[0]: grid_point(row[1], row[2], grid) for row in rows}


def fetch_all(client: httpx.Client, points: list[tuple[float, float]], hours: int) -> dict:
    forecasts: dict[tuple[float, float], PointForecast] = {}
    for start in range(0, len(points), POINTS_PER_REQUEST):
        chunk = points[start : start + POINTS_PER_REQUEST]
        forecasts.update(zip(chunk, open_meteo.fetch_forecasts(client, chunk, hours), strict=True))
    return forecasts


def assess_spray(
    session: Session, client: httpx.Client, thresholds: dict, version: str, now: datetime
) -> IngestionRun:
    """Fetch the forecast for every territory and store one assessment per profile and hour."""
    weather = thresholds["weather"]
    by_territory = territory_points(session, weather["grid_degrees"])
    points = sorted(set(by_territory.values()))
    run = IngestionRun(provider="open_meteo", product="forecast", started_at=now)
    try:
        forecasts = fetch_all(client, points, weather["forecast_hours"]) if points else {}
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        run.status = RunStatus.FAILED
        run.error = f"{type(exc).__name__}: {exc}"[:2000]
    else:
        run.status = RunStatus.SUCCESS
        run.fetched = sum(len(f.hours) for f in forecasts.values())
        run.inserted = 0
        for territory_id, point in by_territory.items():
            for profile_name, profile in thresholds["spray"]["profiles"].items():
                run.inserted += _store(
                    session, territory_id, profile_name, profile, forecasts[point], version, now
                )
    run.finished_at = datetime.now(now.tzinfo)
    session.add(run)
    session.commit()
    return run


def _store(
    session: Session,
    territory_id: int,
    profile_name: str,
    profile: dict,
    forecast: PointForecast,
    version: str,
    fetched_at: datetime,
) -> int:
    lookahead = profile["rain"]["lookahead_hours"]
    rows = []
    for i, hour in enumerate(forecast.hours):
        status, rules = evaluate_hour(
            hour, forecast.hours[i : i + lookahead], forecast.sunrises, profile
        )
        unknown = any(r.status == RuleStatus.UNKNOWN for r in rules)
        rows.append(
            {
                "territory_id": territory_id,
                "profile": profile_name,
                "valid_at": hour.time,
                "status": status,
                "rules": [r.as_dict() for r in rules],
                "weather": {**asdict(hour), "time": hour.time.isoformat()},
                "data_quality": DataQuality.PARTIAL if unknown else DataQuality.GOOD,
                "forecast_fetched_at": fetched_at,
                "processing_version": version,
            }
        )
    if not rows:
        return 0
    statement = insert(SprayAssessment).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["territory_id", "profile", "valid_at"],
        set_={
            col: statement.excluded[col]
            for col in (
                "status",
                "rules",
                "weather",
                "data_quality",
                "forecast_fetched_at",
                "processing_version",
            )
        },
    )
    session.execute(statement)
    return len(rows)


def list_spray_hours(
    session: Session, territory_id: int, profile: str, now: datetime
) -> list[SprayAssessment]:
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    return list(
        session.scalars(
            select(SprayAssessment)
            .where(
                SprayAssessment.territory_id == territory_id,
                SprayAssessment.profile == profile,
                SprayAssessment.valid_at >= current_hour,
            )
            .order_by(SprayAssessment.valid_at)
        )
    )
