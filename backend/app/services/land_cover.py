"""What covers each field and the ring around it: trees, crops, grass, water and buildings
(docs/15-land-cover.md)."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from shapely import from_geojson
from shapely.geometry.base import BaseGeometry
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.models import LandCover
from app.providers import worldcover

log = logging.getLogger(__name__)

# Territories with no land cover yet, or whose outline changed since.
PENDING_SQL = text("""
    SELECT t.id, md5(ST_AsBinary(t.geom)) AS outline,
           ST_AsGeoJSON(t.geom) AS area,
           ST_AsGeoJSON(ST_Difference(
               ST_Buffer(t.geom::geography, :ring_m)::geometry, t.geom
           )) AS ring,
           ST_Y(ST_Centroid(t.geom)) AS lat
    FROM territory t
    LEFT JOIN land_cover lc ON lc.territory_id = t.id
    WHERE lc.territory_id IS NULL OR lc.outline <> md5(ST_AsBinary(t.geom))
    ORDER BY t.id
    LIMIT :limit
""")

Counter = Callable[[BaseGeometry], dict[str, int]]


@dataclass(frozen=True)
class Contents:
    """What a field holds, as the rules and the texts use it."""

    trees_share: float
    crops_share: float
    grass_share: float
    water_share: float
    built_m2: float
    built_nearby_m2: float

    def has_buildings(self, config: dict) -> bool:
        return self.built_m2 + self.built_nearby_m2 >= config["built_m2"]

    def wooded(self, config: dict) -> bool:
        return self.trees_share >= config["trees_share"]


def contents(row: LandCover | None) -> Contents | None:
    if row is None:
        return None
    share = row.shares.get
    return Contents(
        trees_share=share("trees", 0) + share("shrubs", 0),
        crops_share=share("crops", 0),
        grass_share=share("grass", 0),
        water_share=share("water", 0) + share("wetland", 0),
        built_m2=row.built_m2,
        built_nearby_m2=row.built_nearby_m2,
    )


def contents_of(session: Session, ids: list[int]) -> dict[int, Contents]:
    rows = session.scalars(select(LandCover).where(LandCover.territory_id.in_(ids)))
    return {row.territory_id: contents(row) for row in rows}


def refresh_land_cover(
    session: Session, config: dict, now: datetime, count: Counter = worldcover.class_counts
) -> dict:
    """Land cover for every territory that lacks it or was redrawn, a few per run."""
    rows = session.execute(
        PENDING_SQL, {"ring_m": config["ring_m"], "limit": config["per_run"]}
    ).all()
    done = failed = 0
    for row in rows:
        try:
            inside = count(from_geojson(row.area))
            around = count(from_geojson(row.ring))
        except Exception as exc:  # noqa: BLE001 - a network or file error waits for the next run
            log.warning("land cover for territory %s not read: %s", row.id, exc)
            failed += 1
            continue
        total = sum(inside.values())
        if total == 0:
            failed += 1
            continue
        pixel = worldcover.pixel_m2(row.lat)
        session.execute(delete(LandCover).where(LandCover.territory_id == row.id))
        session.add(
            LandCover(
                territory_id=row.id,
                shares={name: round(n / total, 4) for name, n in sorted(inside.items())},
                built_m2=round(inside.get("built", 0) * pixel),
                built_nearby_m2=round(around.get("built", 0) * pixel),
                outline=row.outline,
                source=worldcover.SOURCE,
                computed_at=now,
            )
        )
        session.commit()
        done += 1
    return {"land_cover_done": done, "land_cover_failed": failed}
