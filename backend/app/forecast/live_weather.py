"""Live forecast weather: NASA POWER spliced with Open-Meteo (docs/05-fire-forecast.md)."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import numpy as np
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.forecast.fwi import FwiState, next_day
from app.forecast.weather_history import fetch_point
from app.models import IngestionRun, RunStatus, WeatherDay

LOCAL_TZ = "America/Argentina/Buenos_Aires"
POWER = "nasa_power"
OPEN_METEO = "open_meteo"
# POWER publishes once a day; asking more often only costs requests.
POWER_EVERY = timedelta(hours=12)
CORRECTED = ("tmax_c", "rh_pct", "wind_kmh")


@dataclass(frozen=True)
class Day:
    tmax_c: float
    rh_pct: float
    wind_kmh: float
    rain_mm: float


Point = tuple[float, float]


def daily_from_hourly(hourly: dict) -> dict[date, Day]:
    """The training variables from hourly values: max temperature, humidity at that hour,
    mean wind and rain sum, per local day. Days with missing hours are skipped."""
    by_day: dict[date, list[int]] = defaultdict(list)
    for i, time in enumerate(hourly["time"]):
        by_day[date.fromisoformat(time[:10])].append(i)
    days = {}
    for day, hours in by_day.items():
        temp = [hourly["temperature_2m"][i] for i in hours]
        rh = [hourly["relative_humidity_2m"][i] for i in hours]
        wind = [hourly["wind_speed_10m"][i] for i in hours]
        rain = [hourly["precipitation"][i] for i in hours]
        if len(hours) < 24 or None in temp + rh + wind + rain:
            continue
        hottest = int(np.argmax(temp))
        days[day] = Day(temp[hottest], rh[hottest], float(np.mean(wind)), float(np.sum(rain)))
    return days


def fetch_open_meteo(
    client: httpx.Client, url: str, points: list[Point], past_days: int
) -> dict[Point, dict[date, Day]]:
    """Every point in one request: today plus `past_days` before it, in local days."""
    response = client.get(
        url,
        params={
            "latitude": ",".join(str(lat) for lat, _ in points),
            "longitude": ",".join(str(lon) for _, lon in points),
            "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation",
            "past_days": past_days,
            "forecast_days": 1,
            "wind_speed_unit": "kmh",
            "timezone": LOCAL_TZ,
        },
        timeout=60,
    )
    response.raise_for_status()
    body = response.json()
    locations = body if isinstance(body, list) else [body]
    return {p: daily_from_hourly(loc["hourly"]) for p, loc in zip(points, locations, strict=True)}


def bias(power: dict[date, Day], open_meteo: dict[date, Day], min_days: int) -> dict[str, float]:
    """Mean POWER minus Open-Meteo on the days both have; zero if they share too few days."""
    shared = sorted(set(power) & set(open_meteo))
    if len(shared) < min_days:
        return dict.fromkeys(CORRECTED, 0.0)
    return {
        name: float(
            np.mean([getattr(power[d], name) - getattr(open_meteo[d], name) for d in shared])
        )
        for name in CORRECTED
    }


def corrected(day: Day, offsets: dict[str, float]) -> Day:
    return Day(
        tmax_c=day.tmax_c + offsets["tmax_c"],
        rh_pct=float(np.clip(day.rh_pct + offsets["rh_pct"], 1, 100)),
        wind_kmh=max(day.wind_kmh + offsets["wind_kmh"], 0.0),
        rain_mm=day.rain_mm,
    )


def power_days(
    client: httpx.Client, url: str, point: Point, start: date, end: date, cache_dir: Path | None
) -> dict[date, Day]:
    weather = fetch_point(client, url, point[0], point[1], start, end, cache_dir)
    return {
        d: Day(
            weather.tmax_c[i], weather.rh_at_tmax_pct[i], weather.wind_kmh[i], weather.rain_mm[i]
        )
        for i, d in enumerate(weather.days)
        if not np.isnan(
            [weather.tmax_c[i], weather.rh_at_tmax_pct[i], weather.wind_kmh[i], weather.rain_mm[i]]
        ).any()
    }


def stored_days(
    session: Session, point: Point, since: date, source: str | None = None
) -> dict[date, Day]:
    query = select(WeatherDay).where(
        WeatherDay.latitude == point[0], WeatherDay.longitude == point[1], WeatherDay.day >= since
    )
    if source:
        query = query.where(WeatherDay.source == source)
    return {r.day: Day(r.tmax_c, r.rh_pct, r.wind_kmh, r.rain_mm) for r in session.scalars(query)}


def upsert_days(
    session: Session, point: Point, days: dict[date, Day], source: str, now: datetime
) -> None:
    if not days:
        return
    rows = [
        {
            "latitude": point[0],
            "longitude": point[1],
            "day": d,
            "source": source,
            "updated_at": now,
            **vars(v),
        }
        for d, v in days.items()
    ]
    statement = insert(WeatherDay).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["latitude", "longitude", "day"],
        set_={
            c: statement.excluded[c]
            for c in ("source", "tmax_c", "rh_pct", "wind_kmh", "rain_mm", "updated_at")
        },
    )
    session.execute(statement)


def recompute_fwi(session: Session, point: Point, since: date) -> None:
    """FWI codes from `since` on, starting from the stored codes of the day before."""
    previous = session.scalar(
        select(WeatherDay)
        .where(
            WeatherDay.latitude == point[0],
            WeatherDay.longitude == point[1],
            WeatherDay.day < since,
        )
        .order_by(WeatherDay.day.desc())
        .limit(1)
    )
    state = (
        FwiState(previous.ffmc, previous.dmc, previous.dc)
        if previous and previous.ffmc
        else FwiState()
    )
    rows = session.scalars(
        select(WeatherDay)
        .where(
            WeatherDay.latitude == point[0],
            WeatherDay.longitude == point[1],
            WeatherDay.day >= since,
        )
        .order_by(WeatherDay.day)
    )
    for row in rows:
        today = next_day(
            state, row.tmax_c, row.rh_pct, row.wind_kmh, row.rain_mm, row.day.month, point[0]
        )
        row.ffmc, row.dmc, row.dc = today.ffmc, today.dmc, today.dc
        row.isi, row.bui, row.fwi = today.isi, today.bui, today.fwi
        state = today.state


def _power_is_due(session: Session, now: datetime) -> bool:
    last = session.scalar(
        select(IngestionRun.finished_at)
        .where(IngestionRun.provider == POWER, IngestionRun.status == RunStatus.SUCCESS)
        .order_by(IngestionRun.finished_at.desc())
        .limit(1)
    )
    return last is None or now - last > POWER_EVERY


def refresh_weather(
    session: Session,
    client: httpx.Client,
    points: list[Point],
    config: dict,
    root: Path,
    today: date,
) -> list[IngestionRun]:
    """Brings every point up to today. Only the days that changed get their FWI recomputed."""
    now = datetime.now(UTC)
    live = config["live_weather"]
    first = date(config["first_year"], 1, 1)
    changed_from: dict[Point, date] = {}
    runs = []

    if _power_is_due(session, now):
        run = IngestionRun(provider=POWER, product="daily", started_at=now, fetched=0, inserted=0)
        try:
            for point in points:
                last = session.scalar(
                    select(WeatherDay.day)
                    .where(
                        WeatherDay.latitude == point[0],
                        WeatherDay.longitude == point[1],
                        WeatherDay.source == POWER,
                    )
                    .order_by(WeatherDay.day.desc())
                    .limit(1)
                )
                days: dict[date, Day] = {}
                if last is None:
                    # First run: the training years come from the cache, so this is cheap.
                    archive_end = date(config["last_year"], 12, 31)
                    days |= power_days(
                        client,
                        config["weather_url"],
                        point,
                        first,
                        archive_end,
                        root / config["weather_cache_dir"],
                    )
                    start = archive_end + timedelta(days=1)
                else:
                    start = last + timedelta(days=1)
                if start <= today:
                    days |= power_days(client, config["weather_url"], point, start, today, None)
                upsert_days(session, point, days, POWER, now)
                run.fetched += len(days)
                if days:
                    changed_from[point] = min(days)
            run.status = RunStatus.SUCCESS
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            run.status = RunStatus.FAILED
            run.error = f"{type(exc).__name__}: {exc}"[:2000]
        run.finished_at = datetime.now(UTC)
        session.add(run)
        session.commit()
        runs.append(run)

    run = IngestionRun(
        provider=OPEN_METEO, product="daily_for_forecast", started_at=now, fetched=0, inserted=0
    )
    try:
        recent = fetch_open_meteo(client, live["open_meteo_url"], points, live["past_days"])
        since = today - timedelta(days=live["past_days"])
        for point, days in recent.items():
            power = stored_days(session, point, since, POWER)
            offsets = bias(power, days, live["bias_min_days"])
            # POWER wins wherever it has the day; Open-Meteo only fills what is missing.
            fill = {d: corrected(v, offsets) for d, v in days.items() if d not in power}
            upsert_days(session, point, fill, OPEN_METEO, now)
            run.fetched += len(fill)
            if fill:
                changed_from[point] = min(changed_from.get(point, today), min(fill))
        run.status = RunStatus.SUCCESS
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        run.status = RunStatus.FAILED
        run.error = f"{type(exc).__name__}: {exc}"[:2000]

    for point, since in changed_from.items():
        recompute_fwi(session, point, since)
    run.finished_at = datetime.now(UTC)
    session.add(run)
    session.commit()
    runs.append(run)
    return runs
