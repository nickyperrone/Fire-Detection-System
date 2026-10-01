from datetime import date, timedelta

import pytest

from app.forecast.live_weather import Day, bias, corrected, daily_from_hourly
from app.forecast.serve import band_for, factors, point_weather
from app.models import WeatherDay


def hourly_day(day: str, temps: list[float], rh: list[float]) -> dict:
    return {
        "time": [f"{day}T{h:02d}:00" for h in range(24)],
        "temperature_2m": temps,
        "relative_humidity_2m": rh,
        "wind_speed_10m": [10.0] * 12 + [20.0] * 12,
        "precipitation": [0.0] * 23 + [2.5],
    }


def test_daily_values_are_defined_like_training():
    temps = [15.0] * 24
    temps[15] = 31.0  # the hottest hour
    rh = [80.0] * 24
    rh[15] = 28.0  # humidity at that hour, not the daily minimum elsewhere
    rh[5] = 20.0
    (day,) = daily_from_hourly(hourly_day("2026-10-01", temps, rh)).values()
    assert day == Day(tmax_c=31.0, rh_pct=28.0, wind_kmh=15.0, rain_mm=2.5)


def test_incomplete_days_are_skipped():
    hourly = hourly_day("2026-10-01", [20.0] * 24, [50.0] * 24)
    hourly["temperature_2m"][3] = None
    assert daily_from_hourly(hourly) == {}


def test_bias_moves_open_meteo_onto_power():
    days = [date(2026, 9, 1) + timedelta(days=i) for i in range(10)]
    power = {d: Day(30.0, 30.0, 12.0, 0.0) for d in days}
    open_meteo = {d: Day(28.0, 40.0, 15.0, 1.0) for d in days}
    offsets = bias(power, open_meteo, min_days=7)
    assert offsets == {"tmax_c": 2.0, "rh_pct": -10.0, "wind_kmh": -3.0}
    fixed = corrected(Day(25.0, 95.0, 2.0, 4.0), offsets)
    # Humidity is clipped to 100, wind never negative, rain untouched.
    assert fixed == Day(27.0, 85.0, 0.0, 4.0)
    assert bias(dict(list(power.items())[:3]), open_meteo, min_days=7)["tmax_c"] == 0.0


def row(day: date, rain: float, fwi: float = 12.0) -> WeatherDay:
    return WeatherDay(
        day=day,
        tmax_c=30.0,
        rh_pct=25.0,
        wind_kmh=10.0,
        rain_mm=rain,
        ffmc=90.0,
        dmc=30.0,
        dc=300.0,
        isi=8.0,
        bui=45.0,
        fwi=fwi,
    )


def test_point_weather_counts_rain_and_dry_days():
    today = date(2026, 10, 1)
    rows = [row(today - timedelta(days=i), rain=8.0 if i == 12 else 1.0) for i in range(40)][::-1]
    values = point_weather(rows, today, rain_day_mm=5)
    assert values["days_since_rain"] == 12
    assert values["rain_7d_mm"] == pytest.approx(7.0)
    assert values["rain_30d_mm"] == pytest.approx(29.0 + 8.0)
    # Missing today falls back to yesterday; missing both gives nothing.
    assert point_weather(rows[:-1], today, 5)["days_since_rain"] == 11
    assert point_weather(rows[:-2], today, 5) is None


def test_bands_and_factors():
    bands = [
        {"band": "VERY_HIGH", "from": 0.35},
        {"band": "HIGH", "from": 0.15},
        {"band": "MODERATE", "from": 0.05},
        {"band": "LOW", "from": 0.0},
    ]
    assert [band_for(p, bands) for p in (0.01, 0.05, 0.2, 0.5)] == [
        "LOW",
        "MODERATE",
        "HIGH",
        "VERY_HIGH",
    ]
    config = {
        "dry_air_rh_pct": 35,
        "no_rain_days": 10,
        "hot_c": 32,
        "high_fwi": 20,
        "recent_cell_fire_days": 30,
        "burning_month_rate": 1.0,
    }
    values = {
        "fire_days_around_7d": 2.0,
        "days_since_cell_fire": 400.0,
        "rh_pct": 22.0,
        "days_since_rain": 14.0,
        "tmax_c": 25.0,
        "fwi": 8.0,
        "cell_month_fire_rate": 0.1,
    }
    order = ["rh_pct", "fire_days_around_7d", "days_since_rain"]
    assert factors(values, config, order) == [
        {"code": "dry_air", "value": 22.0},
        {"code": "fire_around_7d", "value": 2.0},
        {"code": "no_rain", "value": 14.0},
    ]
