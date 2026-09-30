"""Lightning near each territory (docs/06-goes.md#lightning)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

NEARBY_SQL = text("""
    SELECT t.id AS territory_id,
           count(*) AS flashes,
           min(ST_Distance(t.geom::geography, f.geom::geography)) AS nearest_m,
           max(f.observed_at) AS last_at
    FROM territory t
    JOIN lightning_flash f
      ON ST_DWithin(t.geom::geography, f.geom::geography, :radius_m)
    WHERE t.id = ANY(:ids) AND f.observed_at >= :since
    GROUP BY t.id
""")


@dataclass(frozen=True)
class NearbyLightning:
    flashes: int
    nearest_m: float
    last_at: datetime


def nearby_lightning(
    session: Session, territory_ids: list[int], config: dict, now: datetime
) -> dict[int, NearbyLightning]:
    if not territory_ids:
        return {}
    rows = session.execute(
        NEARBY_SQL,
        {
            "ids": territory_ids,
            "radius_m": config["radius_m"],
            "since": now - timedelta(minutes=config["window_minutes"]),
        },
    ).all()
    return {r.territory_id: NearbyLightning(r.flashes, r.nearest_m, r.last_at) for r in rows}
