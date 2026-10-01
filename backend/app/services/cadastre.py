"""Official parcels, fetched per tile on first view and cached (docs/08-cadastre.md)."""

import json
import math
from datetime import UTC, datetime, timedelta

import httpx
from shapely.geometry import MultiPolygon, Polygon, shape
from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import CadastralParcel, CadastralTile
from app.providers.cadastre_wfs import Parcel, fetch_parcels

PARCEL_AT_SQL = text("""
    SELECT province, department, partida, plano, status, ST_AsGeoJSON(geom) AS geometry
    FROM cadastral_parcel
    WHERE ST_Intersects(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
    ORDER BY ST_Area(geom)
    LIMIT 1
""")


def tile_bbox(z: int, x: int, y: int) -> list[float]:
    """West, south, east, north of a web-map tile."""
    n = 2**z

    def lat(row: int) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * row / n))))

    return [x / n * 360 - 180, lat(y + 1), (x + 1) / n * 360 - 180, lat(y)]


def tile_of(lat: float, lon: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def _overlaps(a: list[float], b: list[float]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _as_multipolygon(geometry: dict) -> MultiPolygon:
    g = shape(geometry)
    return MultiPolygon([g]) if isinstance(g, Polygon) else g


def _store(session: Session, province: str, parcels: list[Parcel], now: datetime) -> None:
    # The WFS can return one parcel as several features (one per piece); they are one row here.
    merged: dict[tuple[int, int], tuple[Parcel, MultiPolygon]] = {}
    for p in parcels:
        key = (p.department, p.partida)
        pieces = _as_multipolygon(p.geometry)
        if key in merged:
            pieces = MultiPolygon([*merged[key][1].geoms, *pieces.geoms])
        merged[key] = (p, pieces)
    rows = [
        {
            "province": province,
            "department": p.department,
            "partida": p.partida,
            "plano": p.plano,
            "status": p.status,
            "geom": func.ST_SetSRID(func.ST_GeomFromText(geometry.wkt), 4326),
            "fetched_at": now,
        }
        for p, geometry in merged.values()
    ]
    for start in range(0, len(rows), 500):
        statement = insert(CadastralParcel).values(rows[start : start + 500])
        statement = statement.on_conflict_do_update(
            index_elements=["province", "department", "partida"],
            set_={c: statement.excluded[c] for c in ("plano", "status", "geom", "fetched_at")},
        )
        session.execute(statement)


def ensure_tile(
    session: Session, client: httpx.Client, config: dict, z: int, x: int, y: int
) -> int:
    """Makes sure the parcels under a map tile are cached. Returns how many were fetched now."""
    zoom = config["tile_zoom"]
    if z < zoom:
        return 0
    # Requests deeper than the cache zoom share their ancestor's cache entry.
    x, y = x >> (z - zoom), y >> (z - zoom)
    bbox = tile_bbox(zoom, x, y)
    fresh_after = datetime.now(UTC) - timedelta(days=config["refresh_days"])
    fetched = 0
    for source in config["sources"]:
        if not _overlaps(bbox, source["bbox"]):
            continue
        cached = session.get(CadastralTile, (source["province"], zoom, x, y))
        if cached and cached.fetched_at > fresh_after:
            continue
        now = datetime.now(UTC)
        parcels = fetch_parcels(client, source, bbox)
        _store(session, source["province"], parcels, now)
        session.merge(
            CadastralTile(
                province=source["province"], z=zoom, x=x, y=y, parcels=len(parcels), fetched_at=now
            )
        )
        session.commit()
        fetched += len(parcels)
    return fetched


def parcel_at(
    session: Session, client: httpx.Client, config: dict, lat: float, lon: float
) -> dict | None:
    """The smallest cached parcel containing the point, as a GeoJSON feature."""
    zoom = config["tile_zoom"]
    ensure_tile(session, client, config, zoom, *tile_of(lat, lon, zoom))
    row = session.execute(PARCEL_AT_SQL, {"lat": lat, "lon": lon}).first()
    if row is None:
        return None
    return {
        "type": "Feature",
        "properties": {
            "province": row.province,
            "department": row.department,
            "partida": row.partida,
            "plano": row.plano,
            "status": row.status,
        },
        "geometry": json.loads(row.geometry),
    }
