"""The affected-area photo of an alert, from what is in the database
(docs/13-notifications.md#the-affected-area-image)."""

from datetime import datetime, timedelta

import httpx
from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from shapely.ops import nearest_points
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import FireEvent, Territory
from app.services.email_text import Danger, _km
from app.vision.area_map import AreaMap, render

FLASHES_SQL = text("""
    SELECT ST_X(f.geom) AS lon, ST_Y(f.geom) AS lat
    FROM lightning_flash f, territory t
    WHERE t.id = :id AND f.observed_at >= :since
      AND ST_DWithin(t.geom::geography, f.geom::geography, :radius_m)
""")


def area_picture(
    session: Session,
    client: httpx.Client,
    territory: Territory,
    dangers: list[Danger],
    wind: tuple[float, float] | None,
    thresholds: dict,
    locale: str,
    now: datetime,
) -> bytes:
    """`wind` is (km/h, degrees it blows from) now at the field."""
    es = locale == "es"
    outline = to_shape(territory.geom)
    fires = []
    for danger in dangers:
        if danger.fire_event_id is not None:
            event = session.get(FireEvent, danger.fire_event_id)
            fires.append((danger, to_shape(event.geom).centroid))
    distance = None
    if fires:
        danger, point = min(fires, key=lambda f: f[0].distance_m)
        if not outline.contains(point):
            near, _ = nearest_points(outline, point)
            distance = (
                (point.x, point.y),
                (near.x, near.y),
                f"{_km(danger.distance_m, locale)} km",
            )
    lightning = []
    if any(d.kind == "lightning" for d in dangers):
        config = thresholds["lightning"]
        rows = session.execute(
            FLASHES_SQL,
            {
                "id": territory.id,
                "since": now - timedelta(minutes=config["window_minutes"]),
                "radius_m": config["radius_m"],
            },
        )
        lightning = [(r.lon, r.lat) for r in rows]
    area = AreaMap(
        field=outline,
        lots=[to_shape(lot.geom) for lot in territory.sections],
        fires=[(p.x, p.y) for _, p in fires if isinstance(p, Point)],
        lightning=lightning,
        distance=distance,
        wind=(wind[1], f"{'viento' if es else 'wind'} {wind[0]:.0f} km/h") if wind else None,
    )
    return render(area, client, thresholds["alerts"]["area_map"], "{km} km")
