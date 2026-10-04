from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import func, insert, select

from app.forecast.serve import cells_of, forecast_grid
from app.main import app
from app.models import CellForecast, DataQuality, FireForecast, SprayAssessment
from app.routers.dependencies import http_client

HOURS = 48


def open_meteo(request: httpx.Request) -> httpx.Response:
    start = datetime(2026, 10, 4, 12, tzinfo=UTC)
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(HOURS)]
    lat, lon = float(request.url.params["latitude"]), float(request.url.params["longitude"])
    calm = {
        "time": times,
        "temperature_2m": [22.0] * HOURS,
        "relative_humidity_2m": [60.0] * HOURS,
        "precipitation": [0.0] * HOURS,
        "precipitation_probability": [0] * HOURS,
        "wind_speed_10m": [9.0] * HOURS,
        "wind_direction_10m": [90] * HOURS,
        "wind_gusts_10m": [14.0] * HOURS,
        "cloud_cover": [20] * HOURS,
        "is_day": [1] * HOURS,
    }
    return httpx.Response(
        200,
        json={"latitude": lat, "longitude": lon, "hourly": calm, "daily": {"sunrise": []}},
    )


def test_a_new_field_has_spray_conditions_and_forecast_at_once(client, session, thresholds):
    config = thresholds["forecast"]
    grid = forecast_grid(
        tuple(thresholds["region"]["bbox"]),
        config["cell_degrees"],
        thresholds["territories"]["allowed_area"],
    )
    issued = datetime(2026, 10, 4, 11, tzinfo=UTC)
    session.execute(
        insert(CellForecast),
        [
            {
                "row": row,
                "col": col,
                "horizon_days": horizon,
                "valid_from": date(2026, 10, 5),
                "probability": 0.01 * horizon,
                "factors": [],
                "issued_at": issued,
                "model_version": "hgb-test",
                "data_quality": DataQuality.PARTIAL,
            }
            for row, col in cells_of(grid)
            for horizon in (1, 2, 3)
        ],
    )
    session.commit()
    app.dependency_overrides[http_client] = lambda: httpx.Client(
        transport=httpx.MockTransport(open_meteo)
    )
    ring = [
        [-59.10, -33.00],
        [-59.09, -33.00],
        [-59.09, -32.99],
        [-59.10, -32.99],
        [-59.10, -33.00],
    ]
    field = client.post(
        "/territories", json={"name": "New", "geometry": {"type": "Polygon", "coordinates": [ring]}}
    ).json()

    forecasts = session.scalars(
        select(FireForecast).where(FireForecast.territory_id == field["id"])
    ).all()
    assert sorted(f.horizon_days for f in forecasts) == [1, 2, 3]
    one_day = next(f for f in forecasts if f.horizon_days == 1)
    # Every cell within 10 km counts: more than one cell, so more than the single-cell 1 %.
    assert one_day.probability > 0.01
    assert (one_day.data_quality, one_day.issued_at) == (DataQuality.PARTIAL, issued)

    hours = session.scalar(select(func.count()).where(SprayAssessment.territory_id == field["id"]))
    assert hours == HOURS * len(thresholds["spray"]["profiles"])
