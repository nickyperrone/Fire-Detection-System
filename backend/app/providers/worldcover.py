"""ESA WorldCover 10 m land cover, read from its public cloud-optimized GeoTIFFs
(docs/15-land-cover.md). A classification of Sentinel-1 and Sentinel-2 images made by ESA with a
machine-learning model; one file per 3° square, named after its south-west corner."""

import json
import math
from dataclasses import dataclass, field

import numpy as np
import rasterio
from rasterio.features import geometry_mask, shapes
from rasterio.windows import from_bounds
from shapely.geometry import box, mapping, shape
from shapely.geometry.base import BaseGeometry

from app.providers.sentinel2 import GDAL_OPTIONS

SOURCE = "ESA WorldCover 10 m 2021 v200"
URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
    "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
)
# WorldCover codes, by the names the app uses.
CLASSES = {
    10: "trees",
    20: "shrubs",
    30: "grass",
    40: "crops",
    50: "built",
    60: "bare",
    70: "snow",
    80: "water",
    90: "wetland",
    95: "mangroves",
    100: "moss",
}
PIXEL_DEGREES = 1 / 12000
EARTH_M_PER_DEGREE = 111_320


def tile_name(lat: float, lon: float) -> str:
    """The 3° file holding a point: "S36W060" covers 36°S–33°S and 60°W–57°W."""
    south, west = math.floor(lat / 3) * 3, math.floor(lon / 3) * 3
    ns = f"{'S' if south < 0 else 'N'}{abs(south):02d}"
    ew = f"{'W' if west < 0 else 'E'}{abs(west):03d}"
    return ns + ew


def tiles_for(bounds: tuple[float, float, float, float]) -> list[tuple[str, BaseGeometry]]:
    """Every file a box touches, with the 3° square it covers."""
    west, south, east, north = bounds
    found = []
    for lat in range(math.floor(south / 3) * 3, math.floor(north / 3) * 3 + 1, 3):
        for lon in range(math.floor(west / 3) * 3, math.floor(east / 3) * 3 + 1, 3):
            found.append((tile_name(lat, lon), box(lon, lat, lon + 3, lat + 3)))
    return found


def pixel_m2(lat: float) -> float:
    """Ground area of one pixel at a latitude: narrower the further from the equator."""
    side = PIXEL_DEGREES * EARTH_M_PER_DEGREE
    return side * side * math.cos(math.radians(lat))


# What is outlined on the map, with the fewest pixels worth an outline (10 m pixels: 8 are
# 0.08 ha) and how many outlines a field keeps, biggest first.
OUTLINED = {"trees": (10, 20), "built": (50,), "water": (80, 90)}
MIN_PIXELS = {"trees": 8, "built": 2, "water": 8}
MAX_OUTLINES = 300


@dataclass
class Classes:
    counts: dict[str, int] = field(default_factory=dict)
    # GeoJSON features (EPSG:4326) of the outlined classes; filled only when asked for.
    outlines: list[dict] = field(default_factory=list)


def read_classes(area: BaseGeometry, outlines: bool = False) -> Classes:
    """Pixels of each class inside an area, in degrees (EPSG:4326), and with `outlines`, the
    outlines of its trees, buildings and water."""
    found = Classes()
    shapes_found: list[tuple[int, dict]] = []
    with rasterio.Env(**GDAL_OPTIONS):
        for tile, square in tiles_for(area.bounds):
            part = area.intersection(square)
            if part.is_empty:
                continue
            with rasterio.open(f"/vsicurl/{URL.format(tile=tile)}") as src:
                window = from_bounds(*part.bounds, transform=src.transform).round_offsets()
                window = window.round_lengths()
                if window.width < 1 or window.height < 1:
                    continue
                values = src.read(1, window=window)
                transform = src.window_transform(window)
                inside = ~geometry_mask(
                    [mapping(part)], out_shape=values.shape, transform=transform
                )
                codes, n = np.unique(values[inside], return_counts=True)
                for code, count in zip(codes.tolist(), n.tolist(), strict=True):
                    name = CLASSES.get(code)
                    if name:
                        found.counts[name] = found.counts.get(name, 0) + count
                if outlines:
                    shapes_found += _outlines(values, inside, transform)
    shapes_found.sort(key=lambda item: -item[0])
    found.outlines = [feature for _, feature in shapes_found[:MAX_OUTLINES]]
    return found


def _outlines(values, inside, transform) -> list[tuple[int, dict]]:
    out = []
    for name, codes in OUTLINED.items():
        mask = np.isin(values, codes) & inside
        if not mask.any():
            continue
        for geometry, _ in shapes(mask.astype("uint8"), mask=mask, transform=transform):
            polygon = shape(geometry)
            pixels = round(polygon.area / PIXEL_DEGREES**2)
            if pixels < MIN_PIXELS[name]:
                continue
            simple = polygon.simplify(PIXEL_DEGREES / 2)
            out.append(
                (
                    pixels,
                    {
                        "type": "Feature",
                        "properties": {"kind": name, "hectares": round(pixels * 0.01, 2)},
                        "geometry": json_geometry(simple),
                    },
                )
            )
    return out


def json_geometry(polygon: BaseGeometry) -> dict:
    """GeoJSON with coordinates rounded to about a meter, to keep a field's outlines small."""
    return json.loads(json.dumps(mapping(polygon)), parse_float=lambda x: round(float(x), 5))


def class_counts(area: BaseGeometry) -> dict[str, int]:
    return read_classes(area).counts
