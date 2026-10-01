"""Cell-day training table for the fire forecast (docs/05-fire-forecast.md).

Everything is computed on arrays shaped (cells, days) or (rows, columns, days) of the grid, not on
row-by-row tables: ten years of a thousand cells is four million cell-days.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from shapely.geometry import Point
from shapely.prepared import PreparedGeometry
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.forecast.fwi import FwiState, next_day
from app.forecast.weather_history import DailyWeather

FEATURES = [
    "ffmc",
    "dmc",
    "dc",
    "isi",
    "bui",
    "fwi",
    "tmax_c",
    "rh_pct",
    "wind_kmh",
    "rain_mm",
    "rain_7d_mm",
    "rain_30d_mm",
    "days_since_rain",
    "doy_sin",
    "doy_cos",
    "cell_month_fire_rate",
    "days_since_cell_fire",
    "fire_days_around_7d",
    "fire_in_cell_today",
]
DAYS_SINCE_CAP = 3650

# Archive detections by local day (Argentina, UTC-3, no daylight saving since 2009).
DETECTIONS_SQL = text("""
    SELECT ST_X(geom) AS lon, ST_Y(geom) AS lat,
           (acquired_at AT TIME ZONE 'America/Argentina/Buenos_Aires')::date AS day
    FROM historical_detection
    WHERE acquired_at >= :since AND acquired_at < :until
""")


@dataclass(frozen=True)
class Grid:
    west: float
    south: float
    cell: float
    nx: int
    ny: int
    mask: np.ndarray  # (ny, nx) True where the cell center is in Argentina

    def center(self, row: int, col: int) -> tuple[float, float]:
        return self.south + (row + 0.5) * self.cell, self.west + (col + 0.5) * self.cell


def build_grid(bbox: list[float], cell: float, country: PreparedGeometry) -> Grid:
    west, south, east, north = bbox
    nx, ny = round((east - west) / cell), round((north - south) / cell)
    mask = np.zeros((ny, nx), dtype=bool)
    grid = Grid(west, south, cell, nx, ny, mask)
    for row in range(ny):
        for col in range(nx):
            lat, lon = grid.center(row, col)
            mask[row, col] = country.contains(Point(lon, lat))
    return grid


def weather_point(lat: float, lon: float, degrees: float) -> tuple[float, float]:
    return round(round(lat / degrees) * degrees, 4), round(round(lon / degrees) * degrees, 4)


def fire_days(session: Session, grid: Grid, days: list[date]) -> np.ndarray:
    """(ny, nx, days) booleans: at least one detection in the cell that local day."""
    first = days[0]
    fire = np.zeros((grid.ny, grid.nx, len(days)), dtype=bool)
    rows = session.execute(
        DETECTIONS_SQL,
        {
            "since": f"{first:%Y-%m-%d}T03:00:00Z",
            "until": f"{days[-1] + timedelta(days=1):%Y-%m-%d}T03:00:00Z",
        },
    ).all()
    for r in rows:
        col = int((r.lon - grid.west) // grid.cell)
        row = int((r.lat - grid.south) // grid.cell)
        index = (r.day - first).days
        if 0 <= row < grid.ny and 0 <= col < grid.nx and 0 <= index < len(days):
            fire[row, col, index] = True
    return fire


def weather_features(weather: DailyWeather, rain_day_mm: float) -> dict[str, np.ndarray]:
    """FWI codes and rain history for one weather point. Days without data keep yesterday's codes
    and get NaN features, so a gap does not reset the drought codes."""
    n = len(weather.days)
    out = {name: np.full(n, np.nan) for name in FEATURES[:13]}
    state = FwiState()
    since_rain = 0.0
    for i, day in enumerate(weather.days):
        temp, rh = weather.tmax_c[i], weather.rh_at_tmax_pct[i]
        wind, rain = weather.wind_kmh[i], weather.rain_mm[i]
        if np.isnan([temp, rh, wind, rain]).any():
            continue
        today = next_day(state, temp, rh, wind, rain, day.month, weather.latitude)
        state = today.state
        since_rain = 0.0 if rain >= rain_day_mm else since_rain + 1
        for name in ("ffmc", "dmc", "dc", "isi", "bui", "fwi"):
            out[name][i] = getattr(today, name)
        out["tmax_c"][i], out["rh_pct"][i] = temp, rh
        out["wind_kmh"][i], out["rain_mm"][i] = wind, rain
        out["days_since_rain"][i] = since_rain
    rain = np.nan_to_num(weather.rain_mm)
    cumulative = np.concatenate([[0.0], np.cumsum(rain)])
    for window, name in ((7, "rain_7d_mm"), (30, "rain_30d_mm")):
        start = np.maximum(np.arange(1, n + 1) - window, 0)
        out[name] = cumulative[1:] - cumulative[start]
    return out


def history_features(fire: np.ndarray, days: list[date]) -> dict[str, np.ndarray]:
    """Fire-history features per cell and day, using only what was known on that day."""
    ny, nx, nd = fire.shape
    years = np.array([d.year for d in days])
    months = np.array([d.month for d in days])

    # Fire days of the cell in the same month of earlier years, per earlier year.
    month_rate = np.full((ny, nx, nd), np.nan, dtype=np.float32)
    first_year = years.min()
    for year in range(first_year + 1, years.max() + 1):
        earlier = years < year
        for month in range(1, 13):
            past = fire[:, :, earlier & (months == month)].sum(axis=2) / (year - first_year)
            month_rate[:, :, (years == year) & (months == month)] = past[:, :, None]

    days_since = np.full((ny, nx, nd), DAYS_SINCE_CAP, dtype=np.float32)
    running = np.full((ny, nx), DAYS_SINCE_CAP, dtype=np.float32)
    for i in range(nd):
        running = np.where(fire[:, :, i], 0, np.minimum(running + 1, DAYS_SINCE_CAP))
        days_since[:, :, i] = running

    # Fire days in the 3 x 3 cells around, over the last 7 days including today.
    padded = np.pad(fire.astype(np.int16), ((1, 1), (1, 1), (0, 0)))
    around = sum(padded[r : r + ny, c : c + nx, :] for r in range(3) for c in range(3))
    cumulative = np.concatenate(
        [np.zeros((ny, nx, 1), dtype=np.int32), np.cumsum(around, axis=2)], axis=2
    )
    start = np.maximum(np.arange(1, nd + 1) - 7, 0)
    around_7d = (cumulative[:, :, 1:] - cumulative[:, :, start]).astype(np.float32)

    return {
        "cell_month_fire_rate": month_rate,
        "days_since_cell_fire": days_since,
        "fire_days_around_7d": around_7d,
        "fire_in_cell_today": fire.astype(np.float32),
    }


def labels(fire: np.ndarray, horizon: int) -> np.ndarray:
    """(ny, nx, days): a detection in the cell on any of the next `horizon` days; NaN at the end."""
    ny, nx, nd = fire.shape
    y = np.full((ny, nx, nd), np.nan, dtype=np.float32)
    ahead = np.zeros((ny, nx, nd - horizon), dtype=bool)
    for h in range(1, horizon + 1):
        ahead |= fire[:, :, h : nd - horizon + h]
    y[:, :, : nd - horizon] = ahead
    return y


@dataclass(frozen=True)
class Inputs:
    """Everything the rows are read from, computed once for all splits."""

    grid: Grid
    days: list[date]
    horizons: list[int]
    cell_weather: dict[tuple[int, int], dict[str, np.ndarray]]
    seasonal: tuple[np.ndarray, np.ndarray]
    history: dict[str, np.ndarray]
    targets: dict[int, np.ndarray]


def prepare(
    grid: Grid,
    days: list[date],
    weather_by_point: dict[tuple[float, float], DailyWeather],
    fire: np.ndarray,
    horizons: list[int],
    weather_degrees: float,
    rain_day_mm: float,
) -> Inputs:
    by_point = {p: weather_features(w, rain_day_mm) for p, w in weather_by_point.items()}
    doy = np.array([d.timetuple().tm_yday for d in days])
    return Inputs(
        grid=grid,
        days=days,
        horizons=horizons,
        # Cells share their weather point's arrays; nothing is copied per cell.
        cell_weather={
            (int(r), int(c)): by_point[weather_point(*grid.center(r, c), weather_degrees)]
            for r, c in np.argwhere(grid.mask)
        },
        seasonal=(np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)),
        history=history_features(fire, days),
        targets={h: labels(fire, h) for h in horizons},
    )


@dataclass(frozen=True)
class Table:
    X: np.ndarray  # (rows, features) float32
    y: dict[int, np.ndarray]  # horizon -> (rows,) 0/1 as float32
    weight: np.ndarray  # 1 / the chance the row was kept (see `build_table`)
    cell: np.ndarray  # (rows, 2) int16 grid row and column
    day: np.ndarray  # int16 index into `days`


def build_table(
    inputs: Inputs, years: tuple[int, int], negative_share: float, rng: np.random.Generator
) -> Table:
    """Rows of the cell-days in `years`. A row with no fire in any horizon is kept with
    probability `negative_share`; `weight` is 1 / that probability, so training still sees the
    true balance. Use 1.0 for validation and test.

    Two passes: the first only decides which rows to keep, the second writes them into arrays
    allocated once, so no intermediate copy of the table exists.
    """
    days, horizons = inputs.days, inputs.horizons
    nd, longest = len(days), max(horizons)
    year = np.array([d.year for d in days])
    in_years = (year >= years[0]) & (year <= years[1]) & (np.arange(nd) < nd - longest)

    kept: list[tuple[int, int, np.ndarray, np.ndarray]] = []
    for row, col in inputs.cell_weather:
        any_fire = np.zeros(nd, dtype=bool)
        for h in horizons:
            any_fire |= inputs.targets[h][row, col] == 1
        keep = in_years & (any_fire | (rng.random(nd) < negative_share))
        index = np.flatnonzero(keep)
        kept.append((row, col, index, any_fire[index]))

    rows = sum(len(index) for _, _, index, _ in kept)
    X = np.empty((rows, len(FEATURES)), dtype=np.float32)
    y = {h: np.empty(rows, dtype=np.float32) for h in horizons}
    weight = np.empty(rows, dtype=np.float32)
    cell = np.empty((rows, 2), dtype=np.int16)
    day = np.empty(rows, dtype=np.int16)
    at = 0
    for row, col, index, fire_ahead in kept:
        end = at + len(index)
        weather = inputs.cell_weather[(row, col)]
        for j, name in enumerate(FEATURES[:13]):
            X[at:end, j] = weather[name][index]
        X[at:end, 13] = inputs.seasonal[0][index]
        X[at:end, 14] = inputs.seasonal[1][index]
        for j, name in enumerate(FEATURES[15:], start=15):
            X[at:end, j] = inputs.history[name][row, col, index]
        for h in horizons:
            y[h][at:end] = inputs.targets[h][row, col, index]
        weight[at:end] = np.where(fire_ahead, 1.0, 1 / negative_share)
        cell[at:end] = (row, col)
        day[at:end] = index
        at = end
    return Table(X=X, y=y, weight=weight, cell=cell, day=day)
