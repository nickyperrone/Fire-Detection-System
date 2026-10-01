"""Daily weather history from NASA POWER (MERRA-2), one request per point for all years."""

import json
import math
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx
import numpy as np

PARAMETERS = ["T2M_MAX", "QV2M", "PS", "WS10M", "PRECTOTCORR"]
FILL_VALUE = -999.0
# POWER asks clients not to hammer it; one point every half second is plenty for ~80 points.
PAUSE_SECONDS = 0.5


@dataclass(frozen=True)
class DailyWeather:
    """Arrays aligned with `days`. NaN where POWER has no value."""

    latitude: float
    longitude: float
    days: list[date]
    tmax_c: np.ndarray
    rh_at_tmax_pct: np.ndarray
    wind_kmh: np.ndarray
    rain_mm: np.ndarray


def saturation_vapor_pressure_kpa(temp_c: np.ndarray) -> np.ndarray:
    """Tetens formula over water."""
    return 0.6108 * np.exp(17.27 * temp_c / (temp_c + 237.3))


def rh_at_temperature(
    specific_humidity_g_kg: np.ndarray, pressure_kpa: np.ndarray, temp_c: np.ndarray
):
    """Relative humidity the day's water vapor gives at `temp_c`.

    Specific humidity barely changes within a day, so at the daily maximum temperature this is
    close to the afternoon minimum RH, which is what the FWI wants for "noon".
    """
    q = specific_humidity_g_kg / 1000
    vapor_pressure = q * pressure_kpa / (0.622 + 0.378 * q)
    return np.clip(100 * vapor_pressure / saturation_vapor_pressure_kpa(temp_c), 1.0, 100.0)


def fetch_point(
    client: httpx.Client,
    url: str,
    latitude: float,
    longitude: float,
    start: date,
    end: date,
    cache_dir: Path | None,
) -> DailyWeather:
    """`cache_dir` None: no cache, for recent days that POWER is still filling in."""
    cache = (
        cache_dir / f"{latitude:.2f}_{longitude:.2f}_{start:%Y%m%d}_{end:%Y%m%d}.json"
        if cache_dir
        else None
    )
    if cache and cache.exists():
        payload = json.loads(cache.read_text())
    else:
        response = client.get(
            url,
            params={
                "parameters": ",".join(PARAMETERS),
                "community": "AG",
                "latitude": latitude,
                "longitude": longitude,
                "start": f"{start:%Y%m%d}",
                "end": f"{end:%Y%m%d}",
                "format": "JSON",
            },
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(payload))
        time.sleep(PAUSE_SECONDS)
    return parse_point(payload, latitude, longitude, start, end)


def parse_point(
    payload: dict, latitude: float, longitude: float, start: date, end: date
) -> DailyWeather:
    values = payload["properties"]["parameter"]
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]

    def series(name: str) -> np.ndarray:
        raw = values[name]
        column = np.array([raw.get(f"{d:%Y%m%d}", FILL_VALUE) for d in days], dtype=float)
        column[column == FILL_VALUE] = math.nan
        return column

    tmax = series("T2M_MAX")
    return DailyWeather(
        latitude=latitude,
        longitude=longitude,
        days=days,
        tmax_c=tmax,
        rh_at_tmax_pct=rh_at_temperature(series("QV2M"), series("PS"), tmax),
        wind_kmh=series("WS10M") * 3.6,
        rain_mm=series("PRECTOTCORR"),
    )
