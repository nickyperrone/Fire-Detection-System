"""The area where fields can be drawn: Argentina (docs/01-product.md#fields-sections-and-tags)."""

import json
from functools import lru_cache
from pathlib import Path

from shapely import prepared
from shapely.geometry import shape

from app.config import REPO_ROOT

METERS_PER_DEGREE = 111_320


@lru_cache
def allowed_area(path: str, tolerance_m: float) -> prepared.PreparedGeometry:
    """The boundary buffered by `tolerance_m`: Natural Earth 1:10m follows rivers and coasts
    only to within a few hundred meters, and a field on the Uruguay River must still fit."""
    collection = json.loads((REPO_ROOT / Path(path)).read_text())
    (feature,) = collection["features"]
    return prepared.prep(shape(feature["geometry"]).buffer(tolerance_m / METERS_PER_DEGREE))
