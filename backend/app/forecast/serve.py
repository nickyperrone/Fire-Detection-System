"""Issue the fire forecast for every cell and field from live data (docs/05-fire-forecast.md)."""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.boundaries import allowed_area
from app.forecast.dataset import DAYS_SINCE_CAP, FEATURES, Grid, build_grid, weather_point
from app.models import CellForecast, DataQuality, FireForecast, WeatherDay

LOCAL_DAY = "(acquired_at AT TIME ZONE 'America/Argentina/Buenos_Aires')::date"
CELL = (
    "floor((ST_X(geom) - :west) / :cell)::int AS col, "
    "floor((ST_Y(geom) - :south) / :cell)::int AS row"
)
RECENT_FIRE_DAYS_SQL = text(f"""
    SELECT DISTINCT {CELL}, {LOCAL_DAY} AS day
    FROM historical_detection WHERE acquired_at >= :since
""")
LAST_FIRE_SQL = text(f"""
    SELECT {CELL}, max({LOCAL_DAY}) AS day FROM historical_detection GROUP BY 1, 2
""")
MONTH_FIRE_DAYS_SQL = text(f"""
    SELECT {CELL}, count(DISTINCT {LOCAL_DAY}) AS days
    FROM historical_detection
    WHERE extract(month FROM {LOCAL_DAY}) = :month
      AND extract(year FROM {LOCAL_DAY}) BETWEEN :first_year AND :last_year
    GROUP BY 1, 2
""")
# The box test (`&&`, served by the spatial index) discards far cells before the exact
# distance on the spheroid, which is the slow part.
TERRITORY_CELLS_SQL = text("""
    SELECT t.id AS territory_id, c.idx
    FROM territory t,
         unnest(CAST(:lons AS float8[]), CAST(:lats AS float8[]), CAST(:idx AS int[]))
             AS c(lon, lat, idx)
    WHERE (CAST(:ids AS bigint[]) IS NULL OR t.id = ANY(CAST(:ids AS bigint[])))
      AND t.geom && ST_Expand(ST_SetSRID(ST_MakePoint(c.lon, c.lat), 4326), :radius_deg)
      AND ST_DWithin(
          t.geom::geography, ST_SetSRID(ST_MakePoint(c.lon, c.lat), 4326)::geography, :radius_m
      )
""")
# Degrees that cover the radius in any direction: a degree of longitude is shorter than one of
# latitude, by cos(latitude); 0.75 holds down to 41° S.
METERS_PER_DEGREE_LON_MIN = 111_320 * 0.75


@lru_cache
def forecast_grid(bbox: tuple[float, ...], cell: float, boundary: str) -> Grid:
    return build_grid(list(bbox), cell, allowed_area(boundary, 0))


def cells_of(grid: Grid) -> list[tuple[int, int]]:
    return [(int(r), int(c)) for r, c in np.argwhere(grid.mask)]


@lru_cache(maxsize=8)
def _load(path: Path, mtime: float) -> dict:
    # mtime is part of the key, so a retrained model is picked up without restarting the worker.
    return joblib.load(path)


def load_models(model_dir: Path, horizons: list[int]) -> dict[int, dict]:
    paths = {h: model_dir / f"fire_forecast_h{h}.joblib" for h in horizons}
    return {h: _load(p, p.stat().st_mtime) for h, p in paths.items()}


def point_weather(
    rows: list[WeatherDay], today: date, rain_day_mm: float
) -> dict[str, float] | None:
    """Today's weather features of one point, defined as in training. Falls back to yesterday
    when today's row is missing; None when neither exists."""
    by_day = {r.day: r for r in rows}
    current = by_day.get(today) or by_day.get(today - timedelta(days=1))
    if current is None or current.fwi is None:
        return None
    past = [r for r in rows if r.day <= current.day]

    def rain_within(days: int) -> float:
        return sum(r.rain_mm for r in past if (current.day - r.day).days < days)

    last_rain = max((r.day for r in past if r.rain_mm >= rain_day_mm), default=None)
    return {
        **{name: getattr(current, name) for name in ("ffmc", "dmc", "dc", "isi", "bui", "fwi")},
        "tmax_c": current.tmax_c,
        "rh_pct": current.rh_pct,
        "wind_kmh": current.wind_kmh,
        "rain_mm": current.rain_mm,
        "rain_7d_mm": rain_within(7),
        "rain_30d_mm": rain_within(30),
        "days_since_rain": float((current.day - last_rain).days) if last_rain else 365.0,
    }


def fire_history_features(
    session: Session, grid: Grid, today: date, first_year: int
) -> dict[tuple[int, int], dict[str, float]]:
    """The four history features for every cell, with SQL aggregations instead of loading ten
    years of detections."""
    params = {"west": grid.west, "south": grid.south, "cell": grid.cell}
    recent: dict[tuple[int, int], set[date]] = defaultdict(set)
    since = datetime.combine(today - timedelta(days=7), datetime.min.time(), tzinfo=UTC)
    for r in session.execute(RECENT_FIRE_DAYS_SQL, {**params, "since": since}):
        recent[(r.row, r.col)].add(r.day)
    last = {(r.row, r.col): r.day for r in session.execute(LAST_FIRE_SQL, params)}
    month = {
        (r.row, r.col): r.days
        for r in session.execute(
            MONTH_FIRE_DAYS_SQL,
            {**params, "month": today.month, "first_year": first_year, "last_year": today.year - 1},
        )
    }
    earlier_years = max(today.year - first_year, 1)
    week = {today - timedelta(days=i) for i in range(7)}
    features = {}
    for row, col in cells_of(grid):
        around = sum(
            len(recent.get((row + dr, col + dc), set()) & week)
            for dr in (-1, 0, 1)
            for dc in (-1, 0, 1)
        )
        last_day = last.get((row, col))
        features[(row, col)] = {
            "cell_month_fire_rate": month.get((row, col), 0) / earlier_years,
            "days_since_cell_fire": float(
                min((today - last_day).days, DAYS_SINCE_CAP) if last_day else DAYS_SINCE_CAP
            ),
            "fire_days_around_7d": float(around),
            "fire_in_cell_today": float(today in recent.get((row, col), set())),
        }
    return features


def factors(values: dict[str, float], config: dict, order: list[str]) -> list[dict]:
    """Plain conditions that hold today, most important feature first."""
    held = []
    if values["fire_days_around_7d"] > 0:
        held.append(("fire_days_around_7d", "fire_around_7d", values["fire_days_around_7d"]))
    if values["days_since_cell_fire"] <= config["recent_cell_fire_days"]:
        held.append(("days_since_cell_fire", "recent_cell_fire", values["days_since_cell_fire"]))
    if values["rh_pct"] < config["dry_air_rh_pct"]:
        held.append(("rh_pct", "dry_air", values["rh_pct"]))
    if values["days_since_rain"] >= config["no_rain_days"]:
        held.append(("days_since_rain", "no_rain", values["days_since_rain"]))
    if values["tmax_c"] >= config["hot_c"]:
        held.append(("tmax_c", "hot", values["tmax_c"]))
    if values["fwi"] >= config["high_fwi"]:
        held.append(("fwi", "high_fwi", values["fwi"]))
    if values["cell_month_fire_rate"] >= config["burning_month_rate"]:
        held.append(("cell_month_fire_rate", "burning_month", values["cell_month_fire_rate"]))
    held.sort(key=lambda h: order.index(h[0]) if h[0] in order else len(order))
    return [{"code": code, "value": round(float(value), 1)} for _, code, value in held[:3]]


def feature_order(bundle: dict) -> list[str]:
    """Features by importance in the saved model, most important first."""
    importance = bundle.get("importance") or {}
    return sorted(importance, key=importance.get, reverse=True) or FEATURES


def band_for(probability: float, bands: list[dict]) -> str:
    return next(b["band"] for b in bands if probability >= b["from"])


def issue_forecast(
    session: Session, thresholds: dict, root: Path, today: date, version: str
) -> dict:
    config = thresholds["forecast"]
    grid = forecast_grid(
        tuple(thresholds["region"]["bbox"]),
        config["cell_degrees"],
        thresholds["territories"]["allowed_area"],
    )
    cells = cells_of(grid)
    models = load_models(root / config["model_dir"], config["horizons_days"])
    weather = defaultdict(list)
    for row in session.scalars(
        select(WeatherDay)
        .where(WeatherDay.day >= today - timedelta(days=400))
        .order_by(WeatherDay.day)
    ):
        weather[(row.latitude, row.longitude)].append(row)
    point_values = {
        p: point_weather(rows, today, config["rain_day_mm"]) for p, rows in weather.items()
    }
    history = fire_history_features(session, grid, today, config["first_year"])

    doy = today.timetuple().tm_yday
    seasonal = {
        "doy_sin": float(np.sin(2 * np.pi * doy / 365.25)),
        "doy_cos": float(np.cos(2 * np.pi * doy / 365.25)),
    }
    values, missing = [], 0
    for row, col in cells:
        point = point_values.get(weather_point(*grid.center(row, col), config["weather_degrees"]))
        missing += point is None
        values.append(
            {**(point or dict.fromkeys(FEATURES[:13], np.nan)), **seasonal, **history[(row, col)]}
        )
    X = np.array([[v[name] for name in FEATURES] for v in values], dtype=np.float32)
    quality = (
        DataQuality.GOOD
        if missing == 0
        else DataQuality.PARTIAL
        if missing < len(cells)
        else DataQuality.NO_DATA
    )

    now = datetime.now(UTC)
    probabilities = {}
    cell_rows = []
    previous = np.zeros(len(cells))
    for h, bundle in sorted(models.items()):
        raw = bundle["model"].predict_proba(X)[:, 1]
        # A fire within 2 days is also a fire within 3: separately calibrated models can break
        # that by a little, so each horizon is at least the one before it.
        probabilities[h] = previous = np.maximum(bundle["calibration"].predict(raw), previous)
        order = feature_order(bundle)
        model_version = f"hgb-{bundle['trained_at'][:10]}"
        for i, (row, col) in enumerate(cells):
            cell_rows.append(
                {
                    "row": row,
                    "col": col,
                    "horizon_days": h,
                    "valid_from": today + timedelta(days=1),
                    "probability": float(probabilities[h][i]),
                    "factors": factors(values[i], config["factors"], order),
                    "issued_at": now,
                    "model_version": model_version,
                    "data_quality": quality,
                }
            )
    session.execute(delete(CellForecast))
    session.execute(insert(CellForecast).values(cell_rows))
    fields = forecast_territories(session, grid, config, version)
    session.commit()
    return {
        "cells": len(cells),
        "territories": fields,
        "data_quality": quality.value,
        "missing_weather_cells": missing,
    }


def forecast_territories(
    session: Session,
    grid: Grid,
    config: dict,
    version: str,
    territory_ids: list[int] | None = None,
) -> int:
    """Each field's forecast from the stored cell forecasts: at least one fire in any cell within
    the radius, 1 - Π(1 - p), with the factors of its riskiest cell. `territory_ids` limits it to
    fields just drawn or changed, which then do not wait for the next hourly run."""
    stored = session.scalars(select(CellForecast)).all()
    if not stored:
        return 0
    cells = sorted({(c.row, c.col) for c in stored})
    index = {cell: i for i, cell in enumerate(cells)}
    by_horizon: dict[int, list[CellForecast]] = defaultdict(lambda: [None] * len(cells))
    for c in stored:
        by_horizon[c.horizon_days][index[(c.row, c.col)]] = c
    centers = [grid.center(r, c) for r, c in cells]
    rows = session.execute(
        TERRITORY_CELLS_SQL,
        {
            "lons": [lon for _, lon in centers],
            "lats": [lat for lat, _ in centers],
            "idx": list(range(len(cells))),
            "radius_m": config["radius_m"],
            "radius_deg": config["radius_m"] / METERS_PER_DEGREE_LON_MIN,
            "ids": territory_ids,
        },
    ).all()
    near: dict[int, list[int]] = defaultdict(list)
    for r in rows:
        near[r.territory_id].append(r.idx)

    replaced = delete(FireForecast)
    if territory_ids is not None:
        replaced = replaced.where(FireForecast.territory_id.in_(territory_ids))
    session.execute(replaced)
    out = []
    for territory_id, idx in near.items():
        for horizon, forecasts in by_horizon.items():
            p = np.array([forecasts[i].probability for i in idx])
            combined = float(1 - np.prod(1 - p))
            riskiest = forecasts[idx[int(np.argmax(p))]]
            out.append(
                {
                    "territory_id": territory_id,
                    "horizon_days": horizon,
                    "valid_from": riskiest.valid_from,
                    "probability": combined,
                    "band": band_for(combined, config["bands"]),
                    "factors": riskiest.factors,
                    "data_quality": riskiest.data_quality,
                    "issued_at": riskiest.issued_at,
                    "model_version": riskiest.model_version,
                    "processing_version": version,
                }
            )
    if out:
        session.execute(insert(FireForecast).values(out))
    return len(near)
