"""Open-Meteo's wind right now on a grid of points, for the wind animation."""

import math

import httpx

from app.providers.open_meteo import FORECAST_URL

# Points per request: the address stays short and one slow point does not sink the others.
BATCH = 100


def fetch_wind(
    client: httpx.Client, points: list[tuple[float, float]]
) -> list[tuple[float, float] | None]:
    """(east, north) wind in km/h at each (latitude, longitude), in order; None where Open-Meteo
    has none. "Direction" is where the wind comes from, so it blows toward the opposite side."""
    out: list[tuple[float, float] | None] = []
    for start in range(0, len(points), BATCH):
        batch = points[start : start + BATCH]
        response = client.get(
            FORECAST_URL,
            params={
                "latitude": ",".join(f"{lat:.3f}" for lat, _ in batch),
                "longitude": ",".join(f"{lon:.3f}" for _, lon in batch),
                "current": "wind_speed_10m,wind_direction_10m",
                "wind_speed_unit": "kmh",
                "timezone": "GMT",
            },
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        for location in body if isinstance(body, list) else [body]:
            current = location.get("current") or {}
            speed, origin = current.get("wind_speed_10m"), current.get("wind_direction_10m")
            if speed is None or origin is None:
                out.append(None)
                continue
            rad = math.radians(origin)
            out.append((-speed * math.sin(rad), -speed * math.cos(rad)))
    return out
