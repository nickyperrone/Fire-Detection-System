"""Fit a hand-drawn field to the property lines (docs/08-cadastre.md#in-the-map)."""

import json
import math
from dataclasses import dataclass, field

import httpx
from shapely import make_valid, wkb
from shapely.geometry import (
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    mapping,
    shape,
)
from shapely.ops import nearest_points
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.cadastre import ensure_tile, tile_of

METERS_PER_DEGREE = 111_320
# Never fetch more than a 3 x 3 block of cache tiles (about 15 x 15 km) for one drawing.
MAX_TILES = 9

COVERED_PARCELS_SQL = text("""
    WITH d AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326) AS g)
    SELECT p.province, p.department, p.partida, p.plano
    FROM cadastral_parcel p, d
    WHERE ST_Intersects(p.geom, d.g)
      AND ST_Area(ST_Intersection(p.geom, d.g)::geography) >= :share * ST_Area(p.geom::geography)
""")

# The union of the parcels with gaps up to 2 x :gap_m closed (roads between parcels), and how much
# it differs from the drawing, as a share of the drawing's area.
PARCEL_UNION_SQL = text("""
    WITH d AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326) AS g),
    u AS (
        SELECT ST_Buffer(ST_Buffer(ST_Union(geom)::geography, :gap_m)::geometry::geography,
                         -:gap_m)::geometry AS g
        FROM cadastral_parcel
        WHERE province = :province AND (department, partida) IN (SELECT * FROM unnest(
            CAST(:departments AS int[]), CAST(:partidas AS bigint[])))
    )
    SELECT ST_AsGeoJSON(u.g, 7) AS geometry,
           ST_Area(ST_SymDifference(u.g, d.g)::geography) / ST_Area(d.g::geography) AS change
    FROM u, d
""")

NEARBY_LINES_SQL = text("""
    WITH d AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326) AS g)
    SELECT ST_AsBinary(ST_Boundary(p.geom)) AS line
    FROM cadastral_parcel p, d
    WHERE ST_DWithin(p.geom::geography, d.g::geography, :tolerance_m)
""")


@dataclass
class SnapResult:
    method: str  # "parcels", "edges" or "none"
    geometry: dict
    parcels: list[dict] = field(default_factory=list)


def _ensure_area(session: Session, client: httpx.Client, cadastre: dict, drawing: Polygon) -> None:
    zoom = cadastre["tile_zoom"]
    west, south, east, north = drawing.bounds
    x0, y0 = tile_of(north, west, zoom)
    x1, y1 = tile_of(south, east, zoom)
    tiles = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)][:MAX_TILES]
    for x, y in tiles:
        ensure_tile(session, client, cadastre, zoom, x, y)


def _by_parcels(session: Session, drawing: Polygon, config: dict) -> SnapResult | None:
    geometry = json.dumps(mapping(drawing))
    parcels = session.execute(
        COVERED_PARCELS_SQL, {"geometry": geometry, "share": config["parcel_cover_share"]}
    ).all()
    if not parcels or len({p.province for p in parcels}) != 1:
        return None
    row = session.execute(
        PARCEL_UNION_SQL,
        {
            "geometry": geometry,
            "gap_m": config["close_gaps_m"],
            "province": parcels[0].province,
            "departments": [p.department for p in parcels],
            "partidas": [p.partida for p in parcels],
        },
    ).first()
    union = shape(json.loads(row.geometry)) if row and row.geometry else None
    if not isinstance(union, Polygon) or row.change > config["max_shape_change"]:
        return None
    return SnapResult(
        method="parcels",
        geometry=mapping(Polygon(union.exterior)),
        parcels=[
            {
                "province": p.province,
                "department": p.department,
                "partida": p.partida,
                "plano": p.plano,
            }
            for p in parcels
        ],
    )


def _by_edges(session: Session, drawing: Polygon, config: dict) -> SnapResult | None:
    tolerance_m = config["edge_tolerance_m"]
    rows = session.execute(
        NEARBY_LINES_SQL, {"geometry": json.dumps(mapping(drawing)), "tolerance_m": tolerance_m}
    ).all()
    if not rows:
        return None
    lines = []
    for r in rows:
        line = wkb.loads(bytes(r.line))
        lines.extend(getattr(line, "geoms", [line]))
    boundary = MultiLineString(lines)
    corners = MultiPoint([c for line in lines for c in line.coords])
    meters_per_lon = METERS_PER_DEGREE * math.cos(math.radians(drawing.centroid.y))

    def distance_m(a: Point, b: Point) -> float:
        return math.hypot((a.x - b.x) * meters_per_lon, (a.y - b.y) * METERS_PER_DEGREE)

    moved = 0
    ring = []
    for lon, lat in drawing.exterior.coords:
        point = Point(lon, lat)
        # A corner drawn near a property corner goes into it, not onto whichever side is closer.
        target = nearest_points(corners, point)[0]
        if distance_m(target, point) > tolerance_m:
            target = nearest_points(boundary, point)[0]
        if distance_m(target, point) <= tolerance_m:
            ring.append((target.x, target.y))
            moved += 1
        else:
            ring.append((lon, lat))
    if moved == 0:
        return None
    fitted = make_valid(Polygon(ring))
    if isinstance(fitted, MultiPolygon):
        fitted = max(fitted.geoms, key=lambda g: g.area)
    if not isinstance(fitted, Polygon) or fitted.is_empty:
        return None
    return SnapResult(method="edges", geometry=mapping(Polygon(fitted.exterior)))


def snap_to_property_lines(
    session: Session, client: httpx.Client, cadastre: dict, geometry: dict
) -> SnapResult:
    """The drawing fitted by the first rule that applies; unchanged when none does."""
    drawing = shape(geometry)
    if not isinstance(drawing, Polygon) or not drawing.is_valid:
        return SnapResult(method="none", geometry=geometry)
    _ensure_area(session, client, cadastre, drawing)
    config = cadastre["snap"]
    return (
        _by_parcels(session, drawing, config)
        or _by_edges(session, drawing, config)
        or SnapResult(method="none", geometry=geometry)
    )
