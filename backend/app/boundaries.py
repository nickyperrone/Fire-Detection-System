"""Argentina: where fields can be drawn and detections count (docs/01-product.md)."""

import json
from functools import lru_cache
from pathlib import Path

from shapely import prepared
from shapely.geometry import Point, mapping, shape

from app.config import REPO_ROOT

METERS_PER_DEGREE = 111_320


@lru_cache
def allowed_area(path: str, tolerance_m: float) -> prepared.PreparedGeometry:
    """The boundary buffered by `tolerance_m`: Natural Earth 1:10m follows rivers and coasts
    only to within a few hundred meters, and a field on the Uruguay River must still fit."""
    collection = json.loads((REPO_ROOT / Path(path)).read_text())
    (feature,) = collection["features"]
    return prepared.prep(shape(feature["geometry"]).buffer(tolerance_m / METERS_PER_DEGREE))


def country_area(thresholds: dict) -> prepared.PreparedGeometry:
    """Where detections and fields count: the country plus the fields' tolerance."""
    config = thresholds["territories"]
    return allowed_area(config["allowed_area"], config["allowed_area_tolerance_m"])


def inside(area: prepared.PreparedGeometry, latitude: float, longitude: float) -> bool:
    return area.contains(Point(longitude, latitude))


@lru_cache
def boundary_geojson(path: str, simplify_m: float) -> dict:
    """The boundary simplified for drawing on the map (about 120 KB down to a few KB)."""
    collection = json.loads((REPO_ROOT / Path(path)).read_text())
    (feature,) = collection["features"]
    geometry = shape(feature["geometry"]).simplify(simplify_m / METERS_PER_DEGREE)
    return {"type": "Feature", "properties": feature["properties"], "geometry": mapping(geometry)}
