"""Open-Meteo hourly forecast, batched for many points in one request."""

from datetime import UTC, datetime

import httpx

from app.providers.records import HourlyWeather, PointForecast

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARIABLES = {
    "temperature_2m": "temperature_c",
    "relative_humidity_2m": "relative_humidity_pct",
    "precipitation": "precipitation_mm",
    "precipitation_probability": "precipitation_probability_pct",
    "wind_speed_10m": "wind_speed_kmh",
    "wind_direction_10m": "wind_direction_deg",
    "wind_gusts_10m": "wind_gusts_kmh",
    "cloud_cover": "cloud_cover_pct",
    "is_day": "is_day",
}


def fetch_forecasts(
    client: httpx.Client, points: list[tuple[float, float]], hours: int
) -> list[PointForecast]:
    """Return one forecast per (latitude, longitude), in the same order as `points`."""
    params = {
        "latitude": ",".join(f"{lat:.4f}" for lat, _ in points),
        "longitude": ",".join(f"{lon:.4f}" for _, lon in points),
        "hourly": ",".join(HOURLY_VARIABLES),
        "daily": "sunrise",
        "forecast_hours": hours,
        "forecast_days": hours // 24 + 2,
        "wind_speed_unit": "kmh",
        "timezone": "GMT",
    }
    response = client.get(FORECAST_URL, params=params, timeout=30)
    response.raise_for_status()
    body = response.json()
    # A single location comes back as an object, several as a list.
    locations = body if isinstance(body, list) else [body]
    return [parse_location(location) for location in locations]


def parse_location(location: dict) -> PointForecast:
    hourly = location["hourly"]
    hours = []
    for i, time in enumerate(hourly["time"]):
        values = {
            name: hourly.get(api_name, [None] * (i + 1))[i]
            for api_name, name in HOURLY_VARIABLES.items()
        }
        is_day = values.pop("is_day")
        hours.append(
            HourlyWeather(
                time=_utc(time), is_day=None if is_day is None else bool(is_day), **values
            )
        )
    return PointForecast(
        latitude=location["latitude"],
        longitude=location["longitude"],
        hours=hours,
        sunrises=[_utc(t) for t in location.get("daily", {}).get("sunrise", [])],
    )


def _utc(iso_minutes: str) -> datetime:
    # timezone=GMT returns naive ISO strings such as "2026-09-29T20:00".
    return datetime.fromisoformat(iso_minutes).replace(tzinfo=UTC)
